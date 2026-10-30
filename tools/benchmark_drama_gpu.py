"""Compare Metal tuning in separate processes, with a 256 MiB allocator cap."""
import os,time,hashlib,json,statistics,argparse
parser=argparse.ArgumentParser(description='Small GPU-only microbenchmark, not full speech synthesis.')
parser.add_argument('--fast',type=int,choices=(0,1),default=0)
parser.add_argument('--wired-mib',type=int,choices=(0,128),default=0)
args=parser.parse_args()
os.environ['MLX_METAL_FAST_SYNCH']=str(args.fast)
os.environ['BENCH_WIRED']=str(args.wired_mib)
import mlx.core as mx
import numpy as np
mx.set_memory_limit(256*1024**2);mx.set_cache_limit(32*1024**2)
mx.set_wired_limit(int(os.environ.get('BENCH_WIRED','0'))*1024**2)
mx.random.seed(928);mx.set_default_device(mx.gpu)
w=mx.random.normal((8,1024,2048)).astype(mx.bfloat16)
w,s,b=mx.quantize(w,group_size=64,bits=4)
x=mx.random.normal((1,1,1,2048)).astype(mx.bfloat16);ix=mx.arange(8).reshape(1,8)
mx.eval(w,s,b,x,ix)
def one():
 y=mx.gather_qmm(x,w,s,b,rhs_indices=ix,transpose=True,group_size=64,bits=4);mx.eval(y);return y
for _ in range(3):one()
t=[]
for _ in range(5):
 start=time.perf_counter()
 for i in range(32):y=one()
 t.append((time.perf_counter()-start)/32)
print(json.dumps(dict(fast=os.environ.get('MLX_METAL_FAST_SYNCH','0'),wired=os.environ.get('BENCH_WIRED','0'),seconds=statistics.median(t),hash=hashlib.sha256(np.asarray(y.astype(mx.float32)).tobytes()).hexdigest(),peak=mx.get_peak_memory())))
