"""Native CUDA workers; local weights, disk offload and independent supervision."""
import json
import math
import os
from pathlib import Path
import runpy
import sys


def arguments_ltx(d):
    root=Path(d['modele']);audio=d.get('audio');frames=int(d['frames'])
    if not 9<=frames<=481 or (frames-1)%8:raise ValueError('LTX attend de 9 à 481 images, au format 8k+1.')
    command=['ltx_pipelines.a2vid_two_stage' if audio else 'ltx_pipelines.ti2vid_two_stages',
        '--checkpoint-path',str(root/'ltx-2.3-22b-dev.safetensors'),
        '--distilled-lora',str(root/'ltx-2.3-22b-distilled-lora-384-1.1.safetensors'),
        '--spatial-upsampler-path',str(root/'ltx-2.3-spatial-upscaler-x2-1.1.safetensors'),
        '--gemma-root',d['gemma'],'--offload','disk','--prompt',d['prompt'],
        '--height',str(max(128,round(d['height']/64)*64)),
        '--width',str(max(128,round(d['width']/64)*64)),
        '--num-frames',str(frames),'--frame-rate','24','--seed',str(d['seed']),
        '--output-path',d['sortie']]
    for image,index,*strength in d['images']:
        frame=frames-1 if index=='last' else int(index);force=float(strength[0] if strength else 1.)
        if not 0<=frame<frames or not math.isfinite(force) or not 0<=force<=1:raise ValueError('Condition d’image LTX invalide.')
        command+=['--image',str(image),str(frame),str(force)]
    if audio:command+=['--audio-path',audio]
    return command


def generer(d):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    import memoire
    import plateforme
    backend='ltx-torch' if d['type']=='ltx' else 'flux-torch'
    reason=plateforme.raison_backend(backend)
    if reason:raise ValueError(reason)
    import torch
    if not torch.cuda.is_available() or torch.cuda.get_device_capability(0)[0]<8:
        raise ValueError('NVIDIA Ampere ou plus récent et un runtime CUDA fonctionnel requis.')
    cap=int(os.environ['STUDIO_ANIMATION_EFFECTIVE_LIMIT'])
    if memoire.disponible()<4*memoire.GIB:raise ValueError('Moins de 4 Gio disponibles : essai refusé.')
    stop=memoire.surveiller(cap)
    total=torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(min(.9,cap/total))
    try:
        if d['type']=='ltx':
            command=arguments_ltx(d);sys.argv=command
            runpy.run_module(command[0],run_name='__main__')
        else:
            from diffusers import Flux2KleinPipeline
            from PIL import Image
            pipe=Flux2KleinPipeline.from_pretrained(d['modele'],torch_dtype=torch.bfloat16,local_files_only=True)
            pipe.enable_sequential_cpu_offload(device='cuda');pipe.vae.enable_tiling()
            refs=[Image.open(path).convert('RGB') for path in d.get('references',[])]
            for seed in d['seeds']:
                print('Portrait FLUX · seed '+str(seed),flush=True)
                result=pipe(prompt=d['prompt'],image=refs or None,width=768,height=1200,
                    num_inference_steps=4,guidance_scale=1.,generator=torch.Generator('cpu').manual_seed(seed))
                target=Path(d['dossier'])/(d['id']+'-'+str(seed)+'.png');tmp=target.with_suffix('.tmp.png')
                try:result.images[0].save(tmp);tmp.replace(target)
                finally:tmp.unlink(missing_ok=True)
    finally:stop.set()


if __name__=='__main__':generer(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
