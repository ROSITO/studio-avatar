"""Compare GEMV int4 and per-projection BF16 GEMM for a video-sized token batch."""
import os,sys,time,statistics,json
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import torch
from animation_quantification import quantifier,LinearQuantifie
if not torch.backends.mps.is_available():raise SystemExit('MPS required')
torch.set_num_threads(4);torch.mps.set_per_process_memory_fraction(.04)
torch.manual_seed(9)
with torch.no_grad():
    w=torch.randn(2048,2048).bfloat16();packed,scales=quantifier(w)
    layer=LinearQuantifie(SimpleNamespace(get=lambda *_:{'packed':packed,'scales':scales}),'w',None,2048,2048)
    x=torch.randn(512,2048,device='mps');times={};outputs={}
    for mode in ('gemv','gemm'):
        os.environ['STUDIO_WAN_Q4_KERNEL']=mode;layer(x);torch.mps.synchronize()
        values=[]
        for _ in range(3):
            start=time.perf_counter();outputs[mode]=layer(x);torch.mps.synchronize();values.append(time.perf_counter()-start)
        times[mode]=statistics.median(values)
    error=((outputs['gemv']-outputs['gemm']).square().mean()/outputs['gemv'].square().mean()).sqrt().item()
    if error>=.02:raise RuntimeError(f'Unexpected numerical difference: {error}')
    print(json.dumps(dict(seconds=times,gain=times['gemv']/times['gemm'],nrmse=error)))
