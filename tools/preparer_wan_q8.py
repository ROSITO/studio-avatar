"""CPU-only, bounded preparation of the int8 weight cache from an offload index."""
import argparse,json,os,sys,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
parser=argparse.ArgumentParser();parser.add_argument('index',type=Path);parser.add_argument('destination',type=Path)
args=parser.parse_args()
import torch
import memoire
from animation_quantification import CachePoidsQuantifies,quantifier,GROUP
from safetensors.torch import save_file
torch.set_num_threads(2)
memoire.surveiller(2*1024**3)
index=json.loads(args.index.read_text());cache=CachePoidsQuantifies(index,args.destination,12*1024**3,bits=8)
keys=[]
for key,info in index.items():
    if not key.startswith('blocks.') or not key.endswith('.weight'):continue
    _,header=cache.source.headers[info['safetensors_file']];shape=header[info['weight_name']]['shape']
    if len(shape)==2 and shape[1]%GROUP==0 and shape[0]%8==0:keys.append(key)
missing=0
for key in keys:
    bias=key.removesuffix('.weight')+'.bias';bias=bias if bias in index else None
    if not cache.fichier(key,bias).exists():
        info=index[key];_,header=cache.source.headers[info['safetensors_file']];n,k=header[info['weight_name']]['shape']
        missing+=int(n*k*(1+4/GROUP))+n*4
if missing and shutil.disk_usage(args.destination).free<missing+2*1024**3:raise RuntimeError('Espace insuffisant pour préparer les poids 8 bits.')
for i,key in enumerate(keys,1):
    bias=key.removesuffix('.weight')+'.bias';bias=bias if bias in index else None
    path=cache.fichier(key,bias)
    if not path.exists():
        with torch.no_grad():
            weight=cache.source[key];codes,meta=quantifier(weight,8);del weight
            tensors={'packed':codes.contiguous(),'scales':meta.contiguous()}
            if bias:tensors['bias']=cache.source[bias].float().contiguous()
            tmp=path.with_suffix('.tmp');save_file(tensors,str(tmp));os.replace(tmp,path)
            del tensors,codes,meta
    if i%32==0 or i==len(keys):print(f'Préparation CPU 8 bits : {i}/{len(keys)}',flush=True)
cache.source.close()
