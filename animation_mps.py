"""Bounded PyTorch replacements for Wan-Animate-2 CUDA-only kernels.

Use float32 real-valued RoPE and query/head-chunked SDPA. No flash-attn,
Triton, complex tensors, float64, torch.compile or full dense attention mask.
The pretrained model is unchanged; this remains an experimental execution port.
"""
import math
import torch
import torch.nn.functional as F


def rope_params(max_seq_len, dim, theta=10000, offset=0):
    positions = torch.arange(max_seq_len, dtype=torch.float32) + offset
    angles = torch.outer(positions, theta ** (-torch.arange(0, dim, 2, dtype=torch.float32) / dim))
    return torch.stack((angles.cos(), angles.sin()), dim=-1)


def rope_apply(x, grid_sizes, freqs, time_stride=1):
    n, c = x.size(2), x.size(3) // 2
    parts = freqs.split([c - 2 * (c // 3), c // 3, c // 3], dim=1)
    output = []
    for i, (f, h, w) in enumerate(grid_sizes.tolist()):
        length = f * h * w
        phase = torch.cat([
            parts[0][:f*time_stride:time_stride].view(f,1,1,-1,2).expand(f,h,w,-1,2),
            parts[1][:h].view(1,h,1,-1,2).expand(f,h,w,-1,2),
            parts[2][:w].view(1,1,w,-1,2).expand(f,h,w,-1,2),
        ], dim=-2).reshape(length,1,c,2)
        pairs = x[i,:length].float().reshape(length,n,c,2)
        real = pairs[...,0]*phase[...,0] - pairs[...,1]*phase[...,1]
        imag = pairs[...,0]*phase[...,1] + pairs[...,1]*phase[...,0]
        rotated = torch.stack((real,imag),dim=-1).flatten(2)
        output.append(torch.cat((rotated,x[i,length:].float())))
    return torch.stack(output)


def sinusoidal_embedding_1d(dim, position):
    half = dim // 2
    angles = torch.outer(position.float(), 10000 ** (-torch.arange(half,device=position.device,dtype=torch.float32)/half))
    return torch.cat((angles.cos(),angles.sin()),dim=1)


def create_block_mask(mask_mod, B=None, H=None, Q_LEN=None, KV_LEN=None, **kwargs):
    # Retain the upstream mask function; materialize only each SDPA query chunk.
    return mask_mod


def _attention(q,k,v,q_lens=None,k_lens=None,mask_mod=None,score_mod=None,scale=None,causal=False,window_size=(-1,-1)):
    batch, queries, heads, _ = q.shape
    keys = k.shape[1]
    if k.shape[2] != heads: raise ValueError('Grouped query attention is not supported by this port.')
    out = torch.zeros((*q.shape[:-1],v.shape[-1]),device=q.device,dtype=q.dtype)
    ki = torch.arange(keys,device=q.device)[None,:]
    # Keep logits/masks bounded independently of the full number of tokens.
    for b in range(batch):
        qlimit = int(q_lens[b]) if q_lens is not None else queries
        klimit = int(k_lens[b]) if k_lens is not None else keys
        for start in range(0,qlimit,64):
            end = min(start+64,qlimit)
            qi = torch.arange(start,end,device=q.device)[:,None]
            allowed = (ki < klimit).expand(end-start,keys)
            if mask_mod is not None: allowed = allowed & mask_mod(b,0,qi,ki)
            if causal: allowed = allowed & (ki <= qi + keys - queries)
            if window_size != (-1,-1):
                left,right=window_size
                if left>=0:allowed=allowed & (ki>=qi+keys-queries-left)
                if right>=0:allowed=allowed & (ki<=qi+keys-queries+right)
            bias = torch.zeros((end-start,keys),device=q.device,dtype=q.dtype)
            if score_mod is not None: bias=score_mod(bias,b,0,qi,ki)
            bias=bias.masked_fill(~allowed,float('-inf'))
            for h in range(0,heads,4):
                value=F.scaled_dot_product_attention(q[b:b+1,start:end,h:h+4].transpose(1,2),
                    k[b:b+1,:,h:h+4].transpose(1,2),v[b:b+1,:,h:h+4].transpose(1,2),attn_mask=bias,scale=scale)
                out[b:b+1,start:end,h:h+4]=value.transpose(1,2)
    return out


def flash_attention(q,k,v,q_lens=None,k_lens=None,dropout_p=0,softmax_scale=None,q_scale=None,
                    causal=False,window_size=(-1,-1),**kwargs):
    if dropout_p:raise ValueError('Inference only: attention dropout must be zero.')
    return _attention(q if q_scale is None else q*q_scale,k,v,q_lens,k_lens,scale=softmax_scale,causal=causal,window_size=window_size)


def flex_attention(q,k,v,q_lens=None,k_lens=None,block_mask=None,score_mod=None,**kwargs):
    return _attention(q,k,v,q_lens,k_lens,mask_mod=block_mask,score_mod=score_mod)


def randn_cpu(*shape,device=None,**kwargs):
    return torch.randn(*shape,device='cpu',**kwargs).to(device)


def lire_video(path):
    import cv2
    import numpy as np
    cap=cv2.VideoCapture(str(path));fps=cap.get(cv2.CAP_PROP_FPS)
    frames=[]
    try:
        while len(frames)<73:
            ok,frame=cap.read()
            if not ok:break
            frames.append(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
    finally:cap.release()
    if not frames or len(frames)>72 or not math.isfinite(fps) or fps<=0:
        raise ValueError('Extrait attendu : 1 à 3 secondes, 24 images/seconde.')
    return np.stack(frames),fps


class EmbeddingDisque(torch.nn.Module):
    """Read only referenced vocabulary rows, preserving the original embedding."""
    def __init__(self, info, num_embeddings, embedding_dim):
        super().__init__()
        self.info=info;self.num_embeddings=num_embeddings;self.embedding_dim=embedding_dim

    def forward(self, ids):
        from safetensors import safe_open
        flat=ids.detach().reshape(-1).to('cpu')
        unique,inverse=torch.unique(flat,sorted=True,return_inverse=True)
        if unique.numel()==0:return torch.empty((*ids.shape,self.embedding_dim),device=ids.device,dtype=torch.float32)
        if unique.min()<0 or unique.max()>=self.num_embeddings:raise ValueError('Indice de vocabulaire invalide.')
        rows=[]
        for row in unique.tolist():
            # Close each file-backed view after copying a single row; the whole
            # vocabulary must never become resident in CPU or unified GPU RAM.
            with safe_open(self.info['safetensors_file'],framework='pt',device='cpu') as handle:
                value=handle.get_slice(self.info['weight_name'])[row:row+1].float().clone()
                rows.append(value)
        selected=torch.cat(rows,dim=0)
        return selected[inverse].reshape(*ids.shape,self.embedding_dim).to(ids.device)
