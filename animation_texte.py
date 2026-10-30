"""Trim masked T5 padding and reuse identical prompt embeddings per pipeline."""
from collections import OrderedDict
import os
import torch


def installer(pipe):
    if os.environ.get('STUDIO_WAN_TEXT_OPTIMIZE','1') == '0':return
    cache=OrderedDict();bytes_used=0

    @torch.no_grad()
    def encoder(prompt,device=None,dtype=None,max_sequence_length=512):
        nonlocal bytes_used
        device=device or pipe._execution_device
        dtype=dtype or pipe.text_encoder.dtype
        prompts=[prompt] if isinstance(prompt,str) else prompt
        tokens=pipe.tokenizer(prompts,padding='max_length',max_length=max_sequence_length,
            truncation=True,add_special_tokens=True,return_attention_mask=True,return_tensors='pt')
        ids,mask=tokens.input_ids,tokens.attention_mask
        lengths=mask.gt(0).sum(dim=1).long()
        # Cache keys describe the actual truncated input, including padding/masks.
        key=(tuple(ids.shape),ids.numpy().tobytes(),mask.numpy().tobytes(),str(dtype),max_sequence_length)
        if key in cache:
            cache.move_to_end(key)
            print('[Wan] Consigne identique : encodage texte réutilisé',flush=True)
            return cache[key].to(device=device,dtype=dtype,copy=True)
        # Keep positions unchanged; remove only trailing columns masked for
        # every item. Sparse/interior masks are retained unchanged.
        columns=mask.gt(0).any(dim=0).nonzero()
        count=int(columns[-1].item())+1 if columns.numel() else 1
        hidden=pipe.text_encoder(ids[:,:count].to(device),mask[:,:count].to(device)).last_hidden_state
        hidden=hidden.to(device=device,dtype=dtype)
        result=torch.stack([torch.cat((row[:length],row.new_zeros(max_sequence_length-int(length),row.shape[1])))
                            for row,length in zip(hidden,lengths)])
        print(f'[Wan] Encodage texte : {count}/{max_sequence_length} positions calculées',flush=True)
        size=result.numel()*result.element_size()
        if size<=32*1024**2:
            while cache and (bytes_used+size>32*1024**2 or len(cache)>=4):
                _,old=cache.popitem(last=False);bytes_used-=old.numel()*old.element_size()
            cache[key]=result.detach().to('cpu',copy=True);bytes_used+=size
        return result

    pipe._get_t5_prompt_embeds=encoder
