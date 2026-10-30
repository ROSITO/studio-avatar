import contextlib
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

import animation


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for folder in ('sources','performances','videos'):(self.root/folder).mkdir()
        (self.root/'sources/avatar.png').write_bytes(b'image')
        (self.root/'performances/jeu.mp4').write_bytes(b'video')
        self.s=types.SimpleNamespace(ICI=self.root,duree=lambda _:10,VERROU=threading.Lock(),TACHES=[],sauver=lambda:None)
        self.a=animation.Atelier(self.s)
        self.data=dict(avatar='avatar.png',video='jeu.mp4',debut=2,duree=1,prompt='A person in a room.')

    def test_published_checkpoint_names(self):
        from lancer_animation import nom_parametre_wan
        self.assertEqual(nom_parametre_wan('blocks.0.cross_attn.add_k_proj.weight'),'blocks.0.block.cross_attn.k_img.weight')
        self.assertEqual(nom_parametre_wan('blocks.12.self_attn.to_out.0.bias'),'blocks.12.block.self_attn.o.bias')
        self.assertEqual(nom_parametre_wan('blocks.1.block.ffn.0.weight'),'blocks.1.block.ffn.0.weight')
        self.assertEqual(nom_parametre_wan('head.head.weight'),'head.head.weight')

    def test_random_default_and_fixed_seed(self):
        self.assertIsInstance(self.a.valider(self.data)['seed'],int)
        self.assertEqual(self.a.valider(dict(self.data,seed=17))['seed'],17)

    def test_untrusted_paths_and_symlink_escape(self):
        for name in ('../jeu.mp4','/jeu.mp4','x\\jeu.mp4','.hidden'):
            with self.subTest(name=name),self.assertRaises(ValueError):self.a.valider(dict(self.data,video=name))
        (self.root/'performances/escape.mp4').symlink_to(self.root/'sources/avatar.png')
        with self.assertRaises(ValueError):self.a.valider(dict(self.data,video='escape.mp4'))

    def test_bounds_and_nonfinite(self):
        for kw in (dict(debut=-1),dict(duree=.5),dict(duree=4),dict(debut=9.5),dict(duree=float('nan')),dict(debut=float('inf')),dict(seed=True),dict(seed=-1),dict(prompt='x'*2001)):
            with self.subTest(kw=kw),self.assertRaises(ValueError):self.a.valider(dict(self.data,**kw))

    def test_description_facultative_utilise_la_photo(self):
        for value in ('', '   '):
            self.assertEqual(self.a.valider(dict(self.data,prompt=value))['prompt'],animation.PROMPT_DEFAUT)
        sans=dict(self.data);sans.pop('prompt')
        self.assertEqual(self.a.valider(sans)['prompt'],animation.PROMPT_DEFAUT)
        self.assertEqual(self.a.valider(self.data)['prompt'],self.data['prompt'])
        # The frontend fallback also works while an older server finishes a job.
        html=(Path(__file__).parent/'index.html').read_text()
        self.assertIn(animation.PROMPT_DEFAUT,html)

    def test_not_ready_does_not_enqueue(self):
        with patch.object(self.a,'etat',return_value=dict(pret=False,raison='Poids manquants')):
            with self.assertRaisesRegex(ValueError,'Poids manquants'):self.a.demander(self.data)
        self.assertEqual(self.s.TACHES,[])

    def test_job_keeps_model_snapshot_and_seed(self):
        with patch.object(self.a,'etat',return_value=dict(pret=True)),patch.object(self.a,'modele',return_value=self.root/'weights'),patch('animation.budget',return_value=1024):
            t=self.a.demander(dict(self.data,seed=20))
        self.assertEqual(t['params']['seed'],20)
        self.assertEqual(t['modeles']['animation']['id'],'wan-animate2')
        self.assertEqual(t['etat'],'en attente');self.assertEqual(len(self.s.TACHES),1)

    def test_budget_reserve_and_pressure(self):
        import memoire
        with patch.dict('os.environ',{'STUDIO_ANIMATION_MAX_RAM_GB':'16'}),patch.object(memoire,'physique',return_value=36*memoire.GIB),patch.object(memoire,'disponible',return_value=16*memoire.GIB),patch.object(memoire,'pression',return_value=1):
            self.assertEqual(animation.budget(),16*memoire.GIB)
        with patch.dict('os.environ',{'STUDIO_ANIMATION_MAX_RAM_GB':'12'}),patch.object(memoire,'physique',return_value=36*memoire.GIB),patch.object(memoire,'disponible',return_value=6*memoire.GIB),patch.object(memoire,'pression',return_value=1):
            self.assertEqual(animation.budget(),12*memoire.GIB)
        with patch.object(memoire,'disponible',return_value=3*memoire.GIB),self.assertRaises(ValueError):animation.budget()
        with patch.object(memoire,'pression',return_value=4),self.assertRaises(ValueError):animation.budget()


try:
    import torch
    import animation_mps as kernels
except ImportError:torch=None


@unittest.skipUnless(torch is not None,'Optional isolated animation runtime')
class KernelTests(unittest.TestCase):
    def test_disk_embedding_matches_bf16_lookup(self):
        from safetensors.torch import save_file
        torch.manual_seed(4)
        weight=torch.randn(137,32).bfloat16()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'embedding.safetensors';save_file({'shared.weight':weight},str(p))
            layer=kernels.EmbeddingDisque(dict(safetensors_file=str(p),weight_name='shared.weight'),137,32)
            ids=torch.tensor([[1,5,1,136,0]])
            torch.testing.assert_close(layer(ids),weight[ids].float(),rtol=0,atol=0)
            if torch.backends.mps.is_available():torch.testing.assert_close(layer(ids.to('mps')).cpu(),weight[ids].float(),rtol=0,atol=0)

    def test_chunked_attention_matches_dense(self):
        torch.manual_seed(42)
        q=torch.randn(1,135,5,16);k=torch.randn(1,151,5,16);v=torch.randn_like(k)
        expected=torch.nn.functional.scaled_dot_product_attention(q.transpose(1,2),k.transpose(1,2),v.transpose(1,2)).transpose(1,2)
        torch.testing.assert_close(kernels.flash_attention(q,k,v),expected,rtol=1e-5,atol=1e-6)

    def test_sparse_mask_score_bias_and_padding(self):
        torch.manual_seed(42)
        q=torch.randn(1,130,5,16);k=torch.randn(1,145,5,16);v=torch.randn_like(k)
        mask=lambda b,h,qi,ki:(qi%3==ki%3)&(qi<127)&(ki<139)
        score=lambda s,b,h,qi,ki:torch.where(ki>70,s-.3,s)
        qi=torch.arange(130)[:,None];ki=torch.arange(145)[None,:]
        bias=score(torch.zeros(130,145),0,0,qi,ki).masked_fill(~mask(0,0,qi,ki),float('-inf'))
        expected=torch.nn.functional.scaled_dot_product_attention(q.transpose(1,2),k.transpose(1,2),v.transpose(1,2),attn_mask=bias).transpose(1,2)
        torch.testing.assert_close(kernels.flex_attention(q,k,v,block_mask=mask,score_mod=score),expected,rtol=1e-5,atol=1e-6)

    def test_real_rope_matches_complex_reference(self):
        x=torch.randn(1,10,2,12);grid=torch.tensor([[2,2,2]])
        phases=kernels.rope_params(8,12)
        out=kernels.rope_apply(x,grid,phases)
        parts=torch.view_as_complex(phases.double()).split([2,2,2],dim=1)
        f,h,w=2,2,2
        z=torch.cat([parts[0][:f].view(f,1,1,-1).expand(f,h,w,-1),parts[1][:h].view(1,h,1,-1).expand(f,h,w,-1),parts[2][:w].view(1,1,w,-1).expand(f,h,w,-1)],dim=-1).reshape(8,1,6)
        expected=torch.view_as_real(torch.view_as_complex(x[0,:8].double().reshape(8,2,6,2))*z).flatten(2).float()
        torch.testing.assert_close(out[0,:8],expected,rtol=1e-5,atol=1e-6)
        torch.testing.assert_close(out[0,8:],x[0,8:])

    @unittest.skipUnless(torch is not None and torch.backends.mps.is_available(),'Apple Silicon only')
    def test_kernels_on_mps(self):
        q=torch.randn(1,133,5,16)
        reference=kernels.flash_attention(q,q,q)
        actual=kernels.flash_attention(q.to('mps'),q.to('mps'),q.to('mps')).cpu()
        torch.testing.assert_close(actual,reference,rtol=1e-4,atol=1e-5)
        x=torch.randn(1,8,2,12);grid=torch.tensor([[2,2,2]]);phases=kernels.rope_params(8,12)
        expected=kernels.rope_apply(x,grid,phases)
        actual=kernels.rope_apply(x.to('mps'),grid,phases.to('mps')).cpu()
        torch.testing.assert_close(actual,expected,rtol=1e-4,atol=1e-5)


@unittest.skipUnless(torch is not None and torch.backends.mps.is_available(),'Isolated Apple Silicon runtime only')
class TransformerTests(unittest.TestCase):
    def test_disk_offload_preserves_reference_cache(self):
        try:from diffusers import WanAnimate2Transformer3DModel
        except ImportError:self.skipTest('Pinned Wan runtime not installed')
        from lancer_animation import charger_disque
        torch.manual_seed(1)
        model=WanAnimate2Transformer3DModel(dim=48,ffn_dim=96,freq_dim=8,text_dim=32,text_len=8,num_heads=4,num_layers=1)
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);model.save_pretrained(tmp/'model');del model
            model=charger_disque(WanAnimate2Transformer3DModel,tmp/'model',tmp/'offload','mps')
            k,v={},{};device='mps'
            with torch.no_grad():
                model([torch.randn(16,2,4,4,device=device)],grid_sizes=torch.tensor([[2,2,2]]),k_cache=k,v_cache=v,
                    clip_fea_ref=torch.randn(1,257,1280,device=device),y_ref=[torch.randn(20,2,4,4,device=device)],
                    context_ref=[torch.randn(8,32,device=device)],seq_len_ref=8,t=torch.ones(1,device=device),method='forward_ref')
                self.assertEqual(len(k),1);self.assertEqual(len(v),1)
                out=model([torch.randn(16,3,4,4,device=device)],k_cache=k,v_cache=v,clip_fea=torch.randn(1,257,1280,device=device),
                    y=[torch.randn(20,3,4,4,device=device)],context=[torch.randn(8,32,device=device)],seq_len=12,t=torch.ones(1,device=device),
                    grid_sizes_ref=torch.tensor([[2,2,2]]),origin_len=5,origin_area=[32,32],method='forward_gen')
            self.assertEqual(tuple(out[0].shape),(16,3,4,4))
            self.assertTrue(torch.isfinite(out[0]).all().item())

    def test_small_pipeline_exports_without_cuda(self):
        try:
            from diffusers import WanAnimate2Pipeline,WanAnimate2Transformer3DModel,AutoencoderKLWan,DPMSolverMultistepScheduler
        except ImportError:self.skipTest('Pinned Wan runtime not installed')
        from transformers import UMT5EncoderModel,UMT5Config,CLIPVisionModel,CLIPVisionConfig,T5TokenizerFast
        from tokenizers import Tokenizer,models,pre_tokenizers
        from PIL import Image
        import cv2,numpy as np
        from diffusers.utils import export_to_video
        from lancer_animation import charger_disque
        tokenizer_object=Tokenizer(models.WordLevel({'<unk>':0,'A':1,'cat':2,'.':3},unk_token='<unk>'))
        tokenizer_object.pre_tokenizer=pre_tokenizers.Whitespace()
        tokenizer=T5TokenizerFast(tokenizer_object=tokenizer_object,unk_token='<unk>')
        components={
            'text_encoder':UMT5EncoderModel(UMT5Config(vocab_size=10032,d_model=32,d_ff=64,num_layers=1,num_heads=4,d_kv=8)),
            'image_encoder':CLIPVisionModel(CLIPVisionConfig(hidden_size=1280,intermediate_size=32,num_hidden_layers=1,num_attention_heads=16,image_size=224,patch_size=14)),
            'transformer':WanAnimate2Transformer3DModel(dim=48,ffn_dim=96,freq_dim=8,text_dim=32,text_len=8,num_heads=4,num_layers=1),
            'vae':AutoencoderKLWan(base_dim=8,num_res_blocks=1)}
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            video=cv2.VideoWriter(str(tmp/'drive.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),24,(64,64))
            for i in range(5):video.write(np.full((64,64,3),40+i*10,dtype=np.uint8))
            video.release()
            for name,module in list(components.items()):
                module.save_pretrained(tmp/name)
                components[name]=charger_disque(type(module),tmp/name,tmp/('disk-'+name),'mps')
            pipe=WanAnimate2Pipeline(**components,tokenizer=tokenizer,scheduler=DPMSolverMultistepScheduler())
            from animation_texte import installer as optimiser_texte
            optimiser_texte(pipe)
            out=pipe(image=Image.new('RGB',(64,64),'gray'),driving_video=str(tmp/'drive.mp4'),prompt='A cat.',height=64,width=64,
                clip_len=5,num_inference_steps=1,guidance_scale=1,max_sequence_length=8,seed=1,generator=torch.Generator().manual_seed(1))
            self.assertEqual(out.frames[0].shape[0],5)
            self.assertTrue(np.isfinite(out.frames[0]).all())
            export_to_video(out.frames[0],str(tmp/'result.mp4'),fps=24)
            self.assertGreater((tmp/'result.mp4').stat().st_size,0)


if __name__=='__main__':unittest.main()
