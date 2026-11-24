"""Resident MLX projections inside Wan's existing PyTorch motion/attention path.

Only the linear projections change backend. Inputs/outputs cross through bounded
CPU buffers; checkpoint Q4 weights stay on the MLX GPU for the whole segment.
"""
import os
import numpy as np
import torch
from animation_quantification import CachePoidsQuantifies
from animation_poids import PoidsDirects


class CacheMLX(CachePoidsQuantifies):
    def __init__(self,index,root,plafond):
        if plafond<16*1024**3:raise ValueError('Le backend MLX résident nécessite un budget borné de 16 Gio.')
        os.environ.setdefault('MLX_METAL_FAST_SYNCH','1')
        import mlx.core as mx
        self.mx=mx
        mx.set_default_device(mx.gpu);mx.set_memory_limit(plafond-2*1024**3)
        mx.set_cache_limit(64*1024**2);mx.set_wired_limit(0)
        super().__init__(index,root,plafond,bits=4)
        self.backend='MLX';self.maximum=min(self.maximum,plafond-4*1024**3)
        self.builder=CachePoidsQuantifies(index,root,plafond,bits=4);self.builder.maximum=0
    def get(self,key,bias_key=None):
        if key in self.pins:self.hits+=1;return self.pins[key]
        self.misses+=1;path=self.fichier(key,bias_key)
        if not path.exists():
            # First-time conversion is still one bounded projection at a time.
            temporary=self.builder.get(key,bias_key)
            del temporary;torch.mps.synchronize();torch.mps.empty_cache()
        names={'packed':'int32','scales':'bfloat16'}
        if bias_key:names['bias']='float32'
        reader=PoidsDirects({n:dict(safetensors_file=str(path),weight_name=n,dtype=d) for n,d in names.items()})
        try:
            packed=reader['packed'];meta=reader['scales'].float().numpy()
            n=meta.shape[1];groups=meta.shape[0]
            # ATen MPS and MLX both store q0 in the least-significant nibble.
            weight=self.mx.array(packed.numpy().view(np.uint32).reshape(n,groups*8))
            scale=meta[:,:,0].T.copy();offset=(meta[:,:,1].T-8*scale).copy()
            values=dict(weight=weight,scales=self.mx.array(scale).astype(self.mx.float16),
                        biases=self.mx.array(offset).astype(self.mx.float16))
            if bias_key:values['bias']=self.mx.array(reader['bias'].numpy())
            self.mx.eval(values)
        finally:reader.close()
        size=sum(v.nbytes for v in values.values())
        if self.octets+size>self.maximum:raise RuntimeError('Poids MLX résidents au-delà du budget prévu.')
        self.pins[key]=values;self.octets+=size
        return values
    def clear(self):
        self.pins.clear();self.octets=0;self.mx.clear_cache();torch.mps.empty_cache()


class LinearMLX(torch.nn.Module):
    def __init__(self,cache,key,bias,in_features,out_features):
        super().__init__();self.cache=cache;self.key=key;self.bias_key=bias
        self.in_features=in_features;self.out_features=out_features
    def forward(self,x):
        mx=self.cache.mx;values=self.cache.get(self.key,self.bias_key)
        host=x.detach().to(device='cpu',dtype=torch.float16).numpy()
        inputs=mx.array(host)
        output=mx.quantized_matmul(inputs,values['weight'],values['scales'],values['biases'],
                                  transpose=True,group_size=64,bits=4).astype(mx.float32)
        if 'bias' in values:output=output+values['bias']
        mx.eval(output)
        # Never retain an activation's NumPy/MLX buffer in a PyTorch graph.
        result=torch.from_numpy(np.array(output,copy=True)).to(x.device)
        return result


def installer(module,index,root,plafond):
    cache=CacheMLX(index,root,plafond);count=0
    for name,child in list(module.named_modules()):
        if name.startswith('blocks.') and isinstance(child,torch.nn.Linear) and child.in_features%64==0 and child.out_features%8==0:
            key=name+'.weight';bias=name+'.bias' if child.bias is not None else None
            module.set_submodule(name,LinearMLX(cache,key,bias,child.in_features,child.out_features));count+=1
    def compact_reference(_module,args,kwargs,_result):
        if kwargs.get('method')=='forward_ref' and len(args)>=4:
            for references in args[2:4]:
                if args[1] in references:references[args[1]]=references[args[1]].to(torch.bfloat16)
        torch.mps.synchronize();torch.mps.empty_cache()
    for block in module.blocks:block.register_forward_hook(compact_reference,with_kwargs=True)
    module._studio_poids_quantifies=cache
    print(f'[Wan MLX] {count} projections · poids résidents sur le GPU · plafond processus {plafond/1024**3:.0f} Gio',flush=True)
    return cache
