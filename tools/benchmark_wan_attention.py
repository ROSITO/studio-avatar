"""Compare bounded attention tiles on small deterministic tensors; no full Wan run."""
import os
from pathlib import Path
import sys
import time
import json
import statistics
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import torch
import animation_mps
if not torch.backends.mps.is_available():raise SystemExit('MPS required.')
torch.set_num_threads(4);torch.mps.set_per_process_memory_fraction(.03)
torch.manual_seed(8)
q=torch.randn(1,768,40,64,device='mps');k=torch.randn_like(q);v=torch.randn_like(q)
results={};outputs={}
with torch.no_grad():
 for legacy in ('1','0'):
  os.environ['STUDIO_WAN_ATTENTION_LEGACY']=legacy
  animation_mps.flash_attention(q,k,v);torch.mps.synchronize()
  samples=[]
  for _ in range(3):
   start=time.perf_counter();outputs[legacy]=animation_mps.flash_attention(q,k,v);torch.mps.synchronize()
   samples.append(time.perf_counter()-start)
  results[legacy]=statistics.median(samples)
 torch.testing.assert_close(outputs['0'],outputs['1'],rtol=1e-4,atol=1e-5)
print(json.dumps(dict(legacy_seconds=results['1'],adaptive_seconds=results['0'],ratio=results['1']/results['0'],numerical_check=True)))
