import importlib.util
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

@unittest.skipUnless(importlib.util.find_spec('torch'),'Optional isolated Wan runtime')
class OptimisationTexteTest(unittest.TestCase):
    def test_t5_reel_padding_identique_et_cache_isole(self):
        import torch
        from transformers import UMT5Config,UMT5EncoderModel
        import animation_texte
        torch.manual_seed(17)
        model=UMT5EncoderModel(UMT5Config(vocab_size=100,d_model=32,d_ff=64,num_layers=1,num_heads=4,d_kv=8)).eval()
        def tokenize(prompts,**kwargs):
            maximum=kwargs['max_length'];ids=torch.zeros(len(prompts),maximum,dtype=torch.long);mask=ids.clone()
            for i,prompt in enumerate(prompts):
                count=min(maximum,len(prompt)+1);ids[i,:count]=torch.arange(1,count+1);mask[i,:count]=1
            return SimpleNamespace(input_ids=ids,attention_mask=mask)
        pipe=SimpleNamespace(text_encoder=model,tokenizer=tokenize,_execution_device='cpu')
        animation_texte.installer(pipe)
        for prompts in (['abcd',''],[''],['a'*50]):
            tokens=tokenize(prompts,max_length=32)
            with torch.no_grad():expected=model(tokens.input_ids,tokens.attention_mask).last_hidden_state
            lengths=tokens.attention_mask.sum(1)
            expected=torch.stack([torch.cat((row[:length],torch.zeros(32-int(length),32))) for row,length in zip(expected,lengths)])
            with patch.object(model,'forward',wraps=model.forward) as forward:
                actual=pipe._get_t5_prompt_embeds(prompts,max_sequence_length=32)
                torch.testing.assert_close(actual,expected,rtol=1e-5,atol=1e-6)
                first=actual.clone();actual.zero_()
                again=pipe._get_t5_prompt_embeds(prompts,max_sequence_length=32)
                torch.testing.assert_close(again,first,rtol=0,atol=0)
                self.assertEqual(forward.call_count,1)
                self.assertEqual(forward.call_args.args[0].shape[1],int(lengths.max()))
                again.zero_()
                torch.testing.assert_close(pipe._get_t5_prompt_embeds(prompts,max_sequence_length=32),first,rtol=0,atol=0)

    def test_attention_adaptive_equivalente_aux_petits_blocs(self):
        import torch
        import animation_mps
        torch.manual_seed(20)
        for device in ['cpu']+(['mps'] if torch.backends.mps.is_available() else []):
            q=torch.randn(1,273,9,16,device=device);k=torch.randn(1,291,9,16,device=device);v=torch.randn_like(k)
            mask=lambda b,h,qi,ki:(qi%2==ki%2)
            for kwargs in ({},{'block_mask':mask}):
                with patch.dict('os.environ',{'STUDIO_WAN_ATTENTION_LEGACY':'1'}):old=animation_mps.flex_attention(q,k,v,**kwargs)
                with patch.dict('os.environ',{'STUDIO_WAN_ATTENTION_LEGACY':'0'}):new=animation_mps.flex_attention(q,k,v,**kwargs)
                torch.testing.assert_close(new,old,rtol=1e-4,atol=1e-5)
