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


def charger_disque(cls, path, cache, device, mixte=False, int4=False, plafond=12*1024**3, int8=False, backend='torch'):
    """Index original safetensors; materialize only each requested tensor, with its selected dtype.

    Accelerate's safetensors offload index accepts a source file and dtype per
    tensor. This avoids both a full CPU checkpoint and a second model copy.
    """
    import torch
    from accelerate import init_empty_weights
    from accelerate.utils import save_offload_index
    from safetensors import safe_open
    path=Path(path);cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    config=cls.load_config(path) if hasattr(cls,'load_config') else cls.config_class.from_pretrained(path,local_files_only=True)
    with init_empty_weights():
        module=cls.from_config(config) if hasattr(cls,'from_config') else cls(config)
    if hasattr(module,'tie_weights'):module.tie_weights()
    if mixte and cls.__name__=='WanAnimate2Transformer3DModel':
        from animation_poids import lineaires_mixtes
        print(f'Calcul BF16 borné : {lineaires_mixtes(module)} projections ; modulation FP32',flush=True)
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
                index[name]=dict(safetensors_file=str(file.resolve()),weight_name=source_name,dtype=str(expected[name].dtype).removeprefix('torch.'))
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
    if (int4 or int8 or backend=='mlx') and cls.__name__=='WanAnimate2Transformer3DModel':
        if backend=='mlx':
            from animation_mlx import installer as installer_mlx
            installer_mlx(module,index,path.parent/'.studio-avatar-q4',plafond)
        else:
            from animation_quantification import installer as installer_quantification
            installer_quantification(module,index,path.parent/('.studio-avatar-q8' if int8 else '.studio-avatar-q4'),plafond,bits=8 if int8 else 4)
    save_offload_index(index,str(cache))
    from accelerate.hooks import AlignDevicesHook, add_hook_to_module, attach_align_device_hook
    from animation_poids import PoidsDirects
    direct=PoidsDirects(index)
    add_hook_to_module(module,AlignDevicesHook(io_same_device=True),append=True)
    attach_align_device_hook(module,execution_device=torch.device(device),offload=True,weights_map=direct,offload_buffers=False)
    module._studio_lecteur=direct
    # Accelerate normally recreates nested dict inputs. Wan's forward_ref mutates
    # these two caches in place and forward_gen consumes the same instances.
    def preserve_cache(hook):
        if hasattr(hook,'skip_keys'):hook.skip_keys=['k_cache','v_cache']
        for child in getattr(hook,'hooks',[]):preserve_cache(child)
    for child in module.modules():
        if hasattr(child,'_hf_hook'):preserve_cache(child._hf_hook)
    return module.eval()




def reglages_animation(d,portrait):
    smoke=d.get('diagnostic_run') is True
    rapide=d.get('profil')=='apercu' and not smoke
    if smoke:
        steps=2 if d.get('mesurer_etape') and (d.get('int4') or d.get('int8')) else 1
    else:
        steps=4 if rapide else 40
    fps=24
    if smoke and not d.get('mesurer_etape'):
        size=(64,96)
    else:
        size=(256,384)
    width,height=size if portrait else size[::-1]
    return steps,fps,width,height


def guidage_animation(d):
    smoke=d.get('diagnostic_run') is True
    return 1 if (smoke and not d.get('mesurer_etape')) or (not smoke and d.get('profil')=='apercu') else 3


def configurer_budget_mps(torch,cap):
    # The MPS fraction uses Metal's recommended working set, not physical RAM.
    # Keep CPU conversion/read buffers inside the same total worker ceiling.
    target=max(1024**3,cap-2*1024**3)
    recommended=torch.mps.recommended_max_memory()
    torch.mps.set_per_process_memory_fraction(min(1.0,target/recommended))
    return min(target,recommended)


def main(request):
    import tempfile
    d=json.loads(Path(request).read_text())
    import memoire
    # Trigger adaptive Metal buffer collection inside our smaller worker budget.
    # PyTorch's default low watermark can exceed this worker's high watermark.
    gpu_target=max(memoire.GIB,min(int(d['max_ram']),memoire.physique()//2)-2*memoire.GIB)
    os.environ.setdefault('PYTORCH_MPS_LOW_WATERMARK_RATIO',str(.3*gpu_target/memoire.physique()))
    import torch
    from diffusers import WanAnimate2Pipeline, WanAnimate2Transformer3DModel, AutoencoderKLWan, DPMSolverMultistepScheduler
    from diffusers.utils import export_to_video, load_image
    from transformers import UMT5EncoderModel, CLIPVisionModel, T5TokenizerFast
    cap=min(int(d['max_ram']),memoire.physique()//2)
    if cap<(2 if d.get('diagnostic_run') is True and not d.get('mesurer_etape') else 10)*memoire.GIB:raise RuntimeError('Budget animation insuffisant.')
    memoire.surveiller(cap,torch.mps.driver_allocated_memory)
    diagnostic()
    torch.set_num_threads(4)
    configurer_budget_mps(torch,cap)
    model=Path(d['model']).resolve()
    # All generated offload files stay next to the model on its external disk.
    with tempfile.TemporaryDirectory(prefix='.studio-animation-',dir=model) as cache:
        cache=Path(cache)
        print('Chargement borné · lectures directes · projections BF16 et modulation FP32 · MPS',flush=True)
        components={}
        for name,cls in [('transformer',WanAnimate2Transformer3DModel),('text_encoder',UMT5EncoderModel),
                         ('image_encoder',CLIPVisionModel),('vae',AutoencoderKLWan)]:
            components[name]=charger_disque(cls,model/name,cache/name,'mps',mixte=os.environ.get('STUDIO_WAN_MIXED','1')=='1',int4=d.get('int4',False),plafond=cap,int8=d.get('int8',False),backend=d.get('backend','torch'))
        pipe=WanAnimate2Pipeline(**components,
            tokenizer=T5TokenizerFast.from_pretrained(model/'tokenizer',local_files_only=True),
            scheduler=DPMSolverMultistepScheduler.from_pretrained(model/'scheduler',local_files_only=True))
        pipe.vae.enable_tiling()
        from animation_texte import installer as optimiser_texte
        optimiser_texte(pipe,model/'.studio-avatar-texte')
        def trace_phase(obj,method,label):
            original=getattr(obj,method)
            def wrapped(*args,**kwargs):
                print('[Wan] '+label,flush=True)
                result=original(*args,**kwargs)
                torch.mps.empty_cache()
                print('[Wan] '+label+' terminé',flush=True)
                return result
            setattr(obj,method,wrapped)
        trace_phase(pipe,'_get_t5_prompt_embeds','Encodage du texte')
        trace_phase(pipe.vae,'encode','Encodage du mouvement')
        trace_phase(pipe.vae,'decode','Décodage du mouvement')
        cache_quantifie=getattr(pipe.transformer,'_studio_poids_quantifies',None)
        if cache_quantifie is not None:
            decode=pipe.vae.decode
            def decoder_sans_cache(*args,**kwargs):
                print(f'[Wan {getattr(cache_quantifie,'backend','Q'+str(cache_quantifie.bits))}] {cache_quantifie.hits} réutilisations, {cache_quantifie.misses} chargements ; {cache_quantifie.octets/1024**3:.2f} Gio retenus',flush=True)
                cache_quantifie.clear();return decode(*args,**kwargs)
            pipe.vae.decode=decoder_sans_cache
        original_forward=pipe.transformer.forward
        last_method=[None]
        def trace_transformer(*args,**kwargs):
            method=kwargs.get('method')
            suivi.avant(method,kwargs.get('is_uncondtion',False))
            if method=='forward_gen' and dernier_pas[0] is None:dernier_pas[0]=time.perf_counter()
            if method!=last_method[0]:
                print('[Wan] '+('Analyse du jeu filmé' if method=='forward_ref' else 'Animation de l’avatar'),flush=True)
                last_method[0]=method
            return original_forward(*args,**kwargs)
        pipe.transformer.forward=trace_transformer
        from PIL import Image
        with Image.open(d['image']) as image:w,h=image.size
        smoke=d.get('diagnostic_run') is True
        steps,fps,width,height=reglages_animation(d,h>=w)
        guidance=guidage_animation(d)
        print(f'[Wan] Profil {d.get("profil","qualite")} · {steps} étapes · {fps} images/s · {width}×{height}',flush=True)
        if smoke:print(f'Diagnostic technique à {steps} étape(s) : qualité visuelle non évaluée.',flush=True)
        import time
        debut_calcul=time.perf_counter();dernier_pas=[None]
        import math
        from animation_progression import SuiviWan
        suivi=SuiviWan(steps,max(1,math.ceil(float(d['seconds'])-1/fps)),len(pipe.transformer.blocks),2 if guidance>1 else 1)
        def couche_terminee(_module,args,_kwargs,_result):suivi.couche(args[1])
        for block in pipe.transformer.blocks:block.register_forward_hook(couche_terminee,with_kwargs=True)
        def progress(_pipe,i,_t,kw):
            suivi.terminer(i)
            maintenant=time.perf_counter()
            print(f'Animation Wan : étape {i+1}/{steps} · étape : {maintenant-(dernier_pas[0] or debut_calcul):.2f} s · pipeline : {maintenant-debut_calcul:.2f} s',flush=True)
            dernier_pas[0]=maintenant;torch.mps.empty_cache();return kw
        result=pipe(image=load_image(d['image']),driving_video=d['video'],prompt=d['prompt'],
            height=height,width=width,clip_len=fps+1,fps=fps,num_inference_steps=steps,guidance_scale=guidance,seed=d['seed'],
            generator=torch.Generator(device='cpu').manual_seed(d['seed']),callback_on_step_end=progress)
        print('Encodage vidéo',flush=True)
        import numpy as np
        if not np.isfinite(result.frames[0]).all():raise RuntimeError('Le modèle a produit des valeurs non finies ; aucune vidéo exportée.')
        export_to_video(result.frames[0],d['output'],fps=fps)


if __name__=='__main__':
    if len(sys.argv)==2 and sys.argv[1]=='--diagnostic':diagnostic()
    elif len(sys.argv)==2:main(sys.argv[1])
    else:raise SystemExit('Usage : lancer_animation.py requete.json | --diagnostic')
