#!/usr/bin/env python3
"""Isolated experimental Wan-Animate-2 runner; offline weights and disk offload."""
import json
import os
import re
from pathlib import Path
import sys


def nom_parametre_wan(name):
    # Published Diffusers shards use canonical attention names; the pinned
    # experimental implementation retains the original Wan module layout.
    name=re.sub(r'^blocks\.(\d+)\.(?!block\.)',r'blocks.\1.block.',name)
    for old,new in [('.to_q.','.q.'),('.to_k.','.k.'),('.to_v.','.v.'),('.to_out.0.','.o.'),
                    ('.add_k_proj.','.k_img.'),('.add_v_proj.','.v_img.'),('.norm_added_k.','.norm_k_img.')]:
        name=name.replace(old,new)
    return name


def diagnostic():
    import torch
    from diffusers import WanAnimate2Pipeline, WanAnimate2Transformer3DModel
    if sys.platform=='darwin' and not torch.backends.mps.is_available():raise RuntimeError('MPS indisponible.')
    if sys.platform!='darwin':raise RuntimeError('Ce port expérimental est actuellement réservé à Apple Silicon.')
    print('Wan-Animate-2 importé · PyTorch '+torch.__version__+' · MPS disponible',flush=True)


def charger_disque(cls, path, cache, device):
    """Index original safetensors; materialize each layer in FP32 only on demand.

    Accelerate's safetensors offload index accepts a source file and dtype per
    tensor. This avoids both a full CPU checkpoint and a second model copy.
    """
    import torch
    from accelerate import init_empty_weights, disk_offload
    from accelerate.utils import save_offload_index
    from safetensors import safe_open
    path=Path(path);cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    config=cls.load_config(path) if hasattr(cls,'load_config') else cls.config_class.from_pretrained(path,local_files_only=True)
    with init_empty_weights():
        module=cls.from_config(config) if hasattr(cls,'from_config') else cls(config)
    if hasattr(module,'tie_weights'):module.tie_weights()
    weights=[p for p in path.glob('*.safetensors') if not p.name.startswith('._')]
    if not weights:raise RuntimeError('Poids safetensors manquants : '+path.name)
    # Index headers only: no tensor is read until its layer's execution hook.
    index={};expected=dict(module.named_parameters())
    for file in sorted(weights):
        with safe_open(str(file),framework='pt',device='cpu') as handle:
            for source_name in handle.keys():
                name=nom_parametre_wan(source_name) if cls.__name__=='WanAnimate2Transformer3DModel' else source_name
                if cls.__name__=='CLIPVisionModel' and name not in expected and name.startswith('vision_model.'):
                    name=name.removeprefix('vision_model.')
                if name not in expected:continue
                if tuple(handle.get_slice(source_name).get_shape())!=tuple(expected[name].shape):
                    raise RuntimeError('Forme de poids incompatible : '+name)
                index[name]=dict(safetensors_file=str(file.resolve()),weight_name=source_name,dtype='float32')
        print('Index des couches : '+path.name+'/'+file.name,flush=True)
    missing=set(expected)-set(index)
    # Tied embedding weights may be absent from safetensors. Bind before checking.
    if missing and hasattr(module,'tie_weights'):
        module.tie_weights();expected=dict(module.named_parameters());missing=set(expected)-set(index)
    if missing:raise RuntimeError('Paramètres absents : '+', '.join(sorted(missing)[:5]))
    # Shared UMT5 embeddings appear under two module paths. Both hooks must
    # address the same on-disk tensor, without duplicating gigabytes of weights.
    canonical={id(param):name for name,param in module.named_parameters()}
    for name,param in module.named_parameters(remove_duplicate=False):
        source=canonical[id(param)]
        if name not in index and source in index:index[name]=dict(index[source])
    if cls.__name__=='UMT5EncoderModel':
        from animation_mps import EmbeddingDisque
        replacements={}
        for name,child in list(module.named_modules(remove_duplicate=False)):
            if isinstance(child,torch.nn.Embedding) and child.num_embeddings>10000:
                key=name+'.weight'
                if key not in index:raise RuntimeError('Dictionnaire vocal absent : '+key)
                replacement=replacements.setdefault(id(child),EmbeddingDisque(index[key],child.num_embeddings,child.embedding_dim))
                module.set_submodule(name,replacement)
        if replacements:print('Vocabulaire texte : lecture des seules entrées utilisées',flush=True)
    save_offload_index(index,str(cache))
    disk_offload(module,str(cache),execution_device=torch.device(device))
    # Accelerate normally recreates nested dict inputs. Wan's forward_ref mutates
    # these two caches in place and forward_gen consumes the same instances.
    def preserve_cache(hook):
        if hasattr(hook,'skip_keys'):hook.skip_keys=['k_cache','v_cache']
        for child in getattr(hook,'hooks',[]):preserve_cache(child)
    for child in module.modules():
        if hasattr(child,'_hf_hook'):preserve_cache(child._hf_hook)
    return module.eval()


def main(request):
    import tempfile
    import torch
    from diffusers import WanAnimate2Pipeline, WanAnimate2Transformer3DModel, AutoencoderKLWan, DPMSolverMultistepScheduler
    from diffusers.utils import export_to_video, load_image
    from transformers import UMT5EncoderModel, CLIPVisionModel, T5TokenizerFast
    import memoire
    d=json.loads(Path(request).read_text());cap=min(int(d['max_ram']),memoire.physique()//2)
    if cap<(2 if d.get('diagnostic_run') is True else 10)*memoire.GIB:raise RuntimeError('Budget animation insuffisant.')
    memoire.surveiller(cap,torch.mps.driver_allocated_memory)
    diagnostic()
    torch.set_num_threads(4)
    torch.mps.set_per_process_memory_fraction(min(.45,cap/memoire.physique()))
    model=Path(d['model']).resolve()
    # All generated offload files stay next to the model on its external disk.
    with tempfile.TemporaryDirectory(prefix='.studio-animation-',dir=model) as cache:
        cache=Path(cache)
        print('Chargement borné · poids sur disque · FP32 · MPS',flush=True)
        components={}
        for name,cls in [('transformer',WanAnimate2Transformer3DModel),('text_encoder',UMT5EncoderModel),
                         ('image_encoder',CLIPVisionModel),('vae',AutoencoderKLWan)]:
            components[name]=charger_disque(cls,model/name,cache/name,'mps')
        pipe=WanAnimate2Pipeline(**components,
            tokenizer=T5TokenizerFast.from_pretrained(model/'tokenizer',local_files_only=True),
            scheduler=DPMSolverMultistepScheduler.from_pretrained(model/'scheduler',local_files_only=True))
        pipe.vae.enable_tiling()
        def trace_phase(obj,method,label):
            original=getattr(obj,method)
            def wrapped(*args,**kwargs):
                print('[Wan] '+label,flush=True)
                result=original(*args,**kwargs)
                print('[Wan] '+label+' terminé',flush=True)
                return result
            setattr(obj,method,wrapped)
        trace_phase(pipe,'_get_t5_prompt_embeds','Encodage du texte')
        trace_phase(pipe.vae,'encode','Encodage du mouvement')
        trace_phase(pipe.vae,'decode','Décodage du mouvement')
        original_forward=pipe.transformer.forward
        last_method=[None]
        def trace_transformer(*args,**kwargs):
            method=kwargs.get('method')
            if method!=last_method[0]:
                print('[Wan] '+('Analyse du jeu filmé' if method=='forward_ref' else 'Animation de l’avatar'),flush=True)
                last_method[0]=method
            return original_forward(*args,**kwargs)
        pipe.transformer.forward=trace_transformer
        from PIL import Image
        with Image.open(d['image']) as image:w,h=image.size
        smoke=d.get('diagnostic_run') is True
        steps=1 if smoke else 40
        width,height=((64,96) if h>=w else (96,64)) if smoke else ((256,384) if h>=w else (384,256))
        if smoke:print('Diagnostic technique à une étape : qualité visuelle non évaluée.',flush=True)
        def progress(_pipe,i,_t,kw):
            print(f'Animation Wan : étape {i+1}/{steps}',flush=True);return kw
        result=pipe(image=load_image(d['image']),driving_video=d['video'],prompt=d['prompt'],
            height=height,width=width,clip_len=25,num_inference_steps=steps,guidance_scale=1 if smoke else 3,seed=d['seed'],
            generator=torch.Generator(device='cpu').manual_seed(d['seed']),callback_on_step_end=progress)
        print('Encodage vidéo',flush=True)
        import numpy as np
        if not np.isfinite(result.frames[0]).all():raise RuntimeError('Le modèle a produit des valeurs non finies ; aucune vidéo exportée.')
        export_to_video(result.frames[0],d['output'],fps=24)


if __name__=='__main__':
    if len(sys.argv)==2 and sys.argv[1]=='--diagnostic':diagnostic()
    elif len(sys.argv)==2:main(sys.argv[1])
    else:raise SystemExit('Usage : lancer_animation.py requete.json | --diagnostic')
