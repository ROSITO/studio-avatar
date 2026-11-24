"""Read individual safetensors directly, without shard mappings or a model copy."""
from collections.abc import Mapping
import json
import os
import struct
import torch


class PoidsDirects(Mapping):
    def __init__(self,index):
        self.index=index;self.files={};self.headers={}
        self.octets=0;self.reads=0
        for info in index.values():
            name=info['safetensors_file']
            if name in self.headers:continue
            with open(name,'rb') as f:
                size=struct.unpack('<Q',f.read(8))[0]
                self.headers[name]=(8+size,json.loads(f.read(size)))
    def __len__(self):return len(self.index)
    def __iter__(self):return iter(self.index)
    def close(self):
        for fd in self.files.values():os.close(fd)
        self.files.clear()
    def __del__(self):self.close()
    def __getitem__(self,key):
        info=self.index[key];name=info['safetensors_file'];base,header=self.headers[name]
        spec=header[info.get('weight_name',key)]
        dtype={'BF16':torch.bfloat16,'F16':torch.float16,'F32':torch.float32,'I64':torch.int64,'I32':torch.int32,'U8':torch.uint8}[spec['dtype']]
        result=torch.empty(spec['shape'],dtype=dtype,device='cpu')
        data=memoryview(result.reshape(-1).view(torch.uint8).numpy()).cast('B')
        if len(data)!=spec['data_offsets'][1]-spec['data_offsets'][0]:raise ValueError('Taille de poids invalide.')
        if name not in self.files:self.files[name]=os.open(name,os.O_RDONLY)
        fd=self.files[name];offset=base+spec['data_offsets'][0];done=0
        while done<len(data):
            if hasattr(os,'preadv'):n=os.preadv(fd,[data[done:]],offset+done)
            else:
                block=os.pread(fd,len(data)-done,offset+done);n=len(block);data[done:done+n]=block
            if not n:raise EOFError('Poids tronqués pendant la lecture.')
            done+=n
        self.reads+=1;self.octets+=done
        return result.to(dtype=getattr(torch,info.get('dtype',str(dtype).removeprefix('torch.'))))


def lineaires_mixtes(module):
    """Use checkpoint BF16 linear weights; keep modulation and outputs in FP32."""
    import types
    import torch.nn.functional as F
    def forward(self,x):
        return F.linear(x.to(self.weight.dtype),self.weight,self.bias).float()
    count=0
    for name,child in module.named_modules():
        if isinstance(child,torch.nn.Linear) and not name.startswith(('time_embedding.','time_projection.')):
            child.to(dtype=torch.bfloat16)
            child.forward=types.MethodType(forward,child);count+=1
    return count
