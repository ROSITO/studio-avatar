"""Experimental packed 4/8-bit weight storage, BF16 GEMM and bounded GPU retention."""
import hashlib
import json
from pathlib import Path
import os
import time
import shutil
import torch
from animation_poids import PoidsDirects

GROUP=64


def quantifier(weight,bits=4):
    n,k=weight.shape
    codes=torch.empty((n,k//(2 if bits==4 else 1)),dtype=torch.uint8)
    meta=torch.empty((k//GROUP,n,2),dtype=torch.bfloat16)
    for begin in range(0,n,128):
        tile=weight[begin:begin+128].float().reshape(-1,k//GROUP,GROUP)
        lo=tile.amin(-1,keepdim=True);scale=(tile.amax(-1,keepdim=True)-lo).clamp_min(1e-6)/((1<<bits)-1)
        q=((tile-lo)/scale).round().clamp_(0,(1<<bits)-1).to(torch.uint8).reshape(-1,k)
        end=begin+q.shape[0]
        codes[begin:end]=((q[:,::2]<<4)|q[:,1::2]) if bits==4 else q
        meta[:,begin:end]=torch.stack((scale.squeeze(-1),lo.squeeze(-1)+(1<<(bits-1))*scale.squeeze(-1)),-1).transpose(0,1)
    return (torch._convert_weight_to_int4pack(codes.to('mps'),2),meta.to('mps')) if bits==4 else (codes,meta)


class CachePoidsQuantifies:
    def __init__(self,index,root,plafond,bits=4):
        self.bits=bits
        self.source=PoidsDirects(index);self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.plafond=plafond
        requested=int(os.environ.get('STUDIO_WAN_WEIGHT_CACHE_MB',os.environ.get('STUDIO_WAN_Q4_CACHE_MB','9216')))
        if not 0<=requested<=9216:raise ValueError('Cache des poids Wan : entre 0 et 9216 Mio.')
        self.maximum=max(0,min(plafond-3*1024**3,requested*1024**2))
        self.watermark=max(256*1024**2,plafond-int(3.5*1024**3))
        self.verifie=0;self.spare=0;self.pressure=0
        self.octets=0;self.pins={};self.hits=0;self.misses=0;self.convertis=0
    def fichier(self,key,bias_key=None):
        info=self.source.index[key];p=Path(info['safetensors_file']);st=p.stat()
        bias_info=self.source.index[bias_key] if bias_key else None
        bias_stat=Path(bias_info['safetensors_file']).stat() if bias_info else None
        identity=[info,str(p.resolve()),st.st_size,st.st_mtime_ns,bias_info,bias_stat.st_mtime_ns if bias_stat else None,GROUP,torch.__version__,'mps-q4-v1']
        if self.bits==8:identity+=['int8']
        return self.root/(hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()+'.safetensors')
    def verifier_memoire(self):
        if time.monotonic()-self.verifie<1 and torch.mps.driver_allocated_memory()<=self.watermark:return
        import memoire
        if torch.mps.driver_allocated_memory()>self.watermark:
            torch.mps.synchronize();torch.mps.empty_cache()
        self.verifie=time.monotonic();self.spare=memoire.disponible();self.pressure=memoire.pression()
        if (self.pressure>=2 and self.spare<5*1024**3) or torch.mps.driver_allocated_memory()>self.watermark:
            released=0
            while self.pins and released<1024**3:
                _,values=self.pins.popitem();size=sum(v.numel()*v.element_size() for v in values.values())
                released+=size;self.octets-=size
            if released:
                del values;torch.mps.synchronize();torch.mps.empty_cache()
                print(f'[Wan Q{self.bits}] {released/1024**3:.2f} Gio libérés pour garder une marge mémoire',flush=True)
    def get(self,key,bias_key=None):
        self.verifier_memoire()
        if torch.mps.driver_allocated_memory()>self.watermark:
            torch.mps.synchronize();torch.mps.empty_cache()
        if key in self.pins:self.hits+=1;return self.pins[key]
        self.misses+=1;path=self.fichier(key,bias_key)
        if not path.exists():
            from safetensors.torch import save_file
            weight=self.source[key]
            with torch.no_grad():packed,scales=quantifier(weight,self.bits)
            del weight
            tensors={'packed':packed.cpu().contiguous(),'scales':scales.cpu().contiguous()}
            if bias_key:tensors['bias']=self.source[bias_key].float().contiguous()
            tmp=path.with_suffix('.tmp');save_file(tensors,str(tmp));os.replace(tmp,path)
            self.convertis+=1
            if self.convertis==1 or self.convertis%16==0:print(f'[Wan Q{self.bits}] {self.convertis} projections préparées sur le disque des modèles',flush=True)
            values={name:value.to('mps') for name,value in tensors.items()}
        else:
            names={'packed':'int32' if self.bits==4 else 'uint8','scales':'bfloat16'}
            if bias_key:names['bias']='float32'
            reader=PoidsDirects({name:dict(safetensors_file=str(path),weight_name=name,dtype=dtype) for name,dtype in names.items()})
            try:values={name:reader[name].to('mps') for name in names}
            finally:reader.close()
        size=sum(v.numel()*v.element_size() for v in values.values())
        # Pin a stable subset, not a thrashing LRU. Leave space for motion caches
        # and attention activations; the external supervisor enforces total RAM.
        if self.spare>=5*1024**3+size and self.octets+size<=self.maximum and torch.mps.driver_allocated_memory()<=self.watermark:
            self.pins[key]=values;self.octets+=size
        return values
    def clear(self):
        self.pins.clear();self.octets=0;torch.mps.empty_cache()


class LinearQuantifie(torch.nn.Module):
    def __init__(self,cache,key,bias,in_features,out_features):
        super().__init__();self.cache=cache;self.key=key;self.bias_key=bias
        self.in_features=in_features;self.out_features=out_features
    def forward(self,x):
        values=self.cache.get(self.key,self.bias_key)
        shape=x.shape[:-1];flat=x.reshape(-1,self.in_features).to(torch.bfloat16).contiguous()
        bits=getattr(self.cache,'bits',4)
        if bits==8 or (flat.shape[0]>=64 and os.environ.get('STUDIO_WAN_Q4_KERNEL','gemm')!='gemv'):
            # MPS int4pack is GEMV-oriented. For video-sized token batches,
            # dequantize just this projection and use the optimized BF16 GEMM.
            # MPS packing swaps the high/low nibble of each row-major byte.
            n=self.out_features;k=self.in_features
            if bits==4:
                raw=values['packed'].view(torch.uint8).reshape(n,k//2)
                weight=torch.stack((raw&15,raw>>4),dim=-1).reshape(n,k).float()
            else:weight=values['packed'].float()
            weight.sub_(1<<(bits-1))
            scale=values['scales'][:,:,0].T.float().unsqueeze(-1)
            zero=values['scales'][:,:,1].T.float().unsqueeze(-1)
            weight.view(n,k//GROUP,GROUP).mul_(scale).add_(zero)
            weight=weight.bfloat16()
            out=torch.nn.functional.linear(flat,weight).float()
        else:
            out=torch._weight_int4pack_mm(flat,values['packed'],GROUP,values['scales']).float()
        if 'bias' in values:out=out+values['bias']
        return out.reshape(*shape,self.out_features)


def installer(module,index,root,plafond,bits=4):
    if bits==4 and not torch._C._dispatch_has_kernel_for_dispatch_key('aten::_weight_int4pack_mm','MPS'):
        raise RuntimeError('Cette version de PyTorch ne fournit pas le calcul int4 natif MPS.')
    cache=CachePoidsQuantifies(index,root,plafond,bits);count=0
    missing=0
    for name,child in module.named_modules():
        if name.startswith('blocks.') and isinstance(child,torch.nn.Linear) and child.in_features%GROUP==0 and child.out_features%8==0:
            key=name+'.weight';bias=name+'.bias' if child.bias is not None else None
            if not cache.fichier(key,bias).exists():missing+=int(child.in_features*child.out_features*(bits/8+4/GROUP))+child.out_features*4
    if missing and shutil.disk_usage(root).free<missing+2*1024**3:
        raise RuntimeError('Espace insuffisant sur le disque des modèles pour préparer Wan en 4 bits.')
    for name,child in list(module.named_modules()):
        if name.startswith('blocks.') and isinstance(child,torch.nn.Linear) and child.in_features%GROUP==0 and child.out_features%8==0:
            key=name+'.weight';bias=name+'.bias' if child.bias is not None else None
            module.set_submodule(name,LinearQuantifie(cache,key,bias,child.in_features,child.out_features));count+=1
    def compact_reference(_module,args,kwargs,result):
        if kwargs.get('method')=='forward_ref' and len(args)>=4:
            layer=args[1]
            for references in args[2:4]:
                if layer in references:references[layer]=references[layer].to(torch.bfloat16)
        # Completing a block lets Metal release its intermediate activations.
        # With resident weights, implicit CPU->GPU copy barriers disappear.
        torch.mps.synchronize();torch.mps.empty_cache()
    for block in module.blocks:
        block.register_forward_hook(compact_reference,with_kwargs=True)
    module._studio_poids_quantifies=cache
    print(f'[Wan Q{bits}] {count} projections {bits} bits ; rétention maximale {cache.maximum/1024**3:.2f} Gio',flush=True)
    return cache
