"""Trim masked T5 padding and reuse identical prompt embeddings per pipeline."""
from collections import OrderedDict
import os
import hashlib
import json
from pathlib import Path
import torch


def installer(pipe,dossier=None):
    if os.environ.get('STUDIO_WAN_TEXT_OPTIMIZE','1') == '0':return
    cache=OrderedDict();bytes_used=0
    disk=Path(dossier) if dossier else None
    fingerprint=None
    if disk is not None and hasattr(pipe.text_encoder,'_studio_lecteur'):
        import transformers
        index=pipe.text_encoder._studio_lecteur.index
        files=sorted({info['safetensors_file'] for info in index.values()})
        signatures=[(name,Path(name).stat().st_size,Path(name).stat().st_mtime_ns) for name in files]
        fingerprint=hashlib.sha256(json.dumps([index,signatures,torch.__version__,transformers.__version__,
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            hashlib.sha256(Path(__file__).with_name('animation_mps.py').read_bytes()).hexdigest()],sort_keys=True).encode()).hexdigest()
        disk.mkdir(parents=True,exist_ok=True)

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
        saved=None
        if fingerprint:
            identity=hashlib.sha256(fingerprint.encode()+repr(key).encode()).hexdigest()
            saved=disk/(identity+'.safetensors')
            if saved.exists():
                from safetensors.torch import load_file
                try:
                    value=load_file(str(saved),device='cpu')['embedding']
                    expected=(ids.shape[0],max_sequence_length,pipe.text_encoder.config.d_model)
                    if tuple(value.shape)!=expected or value.dtype!=dtype or not torch.isfinite(value).all():raise ValueError('Cache texte invalide.')
                    print('[Wan] Encodage texte réutilisé depuis le disque des modèles',flush=True)
                    return value.to(device=device,dtype=dtype,copy=True)
                except (OSError,ValueError,KeyError,RuntimeError):saved.unlink(missing_ok=True)
        # Keep positions unchanged; remove only trailing columns masked for
        # every item. Sparse/interior masks are retained unchanged.
        columns=mask.gt(0).any(dim=0).nonzero()
        count=int(columns[-1].item())+1 if columns.numel() else 1
        hidden=pipe.text_encoder(ids[:,:count].to(device),mask[:,:count].to(device)).last_hidden_state
        hidden=hidden.to(device=device,dtype=dtype)
        result=torch.stack([torch.cat((row[:length],row.new_zeros(max_sequence_length-int(length),row.shape[1])))
                            for row,length in zip(hidden,lengths)])
        print(f'[Wan] Encodage texte : {count}/{max_sequence_length} positions calculées',flush=True)
        if saved is not None:
            from safetensors.torch import save_file
            tmp=saved.with_suffix('.tmp')
            save_file({'embedding':result.detach().to('cpu',copy=True).contiguous()},str(tmp));os.replace(tmp,saved)
        size=result.numel()*result.element_size()
        if size<=32*1024**2:
            while cache and (bytes_used+size>32*1024**2 or len(cache)>=4):
                _,old=cache.popitem(last=False);bytes_used-=old.numel()*old.element_size()
            cache[key]=result.detach().to('cpu',copy=True);bytes_used+=size
        return result

    pipe._get_t5_prompt_embeds=encoder
