"""Compare identical expert rows, with a small fixed IO budget and no GPU."""
import sys,json,struct,time,statistics,argparse
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from drama_lecture import LectureDirecte
parser=argparse.ArgumentParser(description='Small warm-file read benchmark; not a speech benchmark.')
parser.add_argument('model',type=Path)
root=parser.parse_args().model
selection=None
for p in root.glob('model-*.safetensors'):
 with p.open('rb') as f:
  n=struct.unpack('<Q',f.read(8))[0];h=json.loads(f.read(n))
 for k,v in h.items():
  if '.switch_mlp.' in k and k.endswith('.weight') and v['dtype']=='U32':
   row=np.prod(v['shape'][1:])*4
   if row*8<=8*1024**2:
    selection=(p,'uint32',8+n+v['data_offsets'][0],tuple(v['shape']));break
 if selection:break
assert selection
p,dtype,offset,shape=selection
indices=np.array([0,5,12,44,67,98,172,231])
def old():
 b=np.memmap(p,mode='r',dtype=dtype,offset=offset,shape=shape)
 try:return np.array(b[indices],copy=True)
 finally:b._mmap.close()
r=LectureDirecte();times={'mmap':[],'direct':[]}
try:
 expected=old();np.testing.assert_array_equal(expected,r(selection,indices))
 for i in range(6):
  for name,fn in ([('mmap',old),('direct',lambda:r(selection,indices))] if i%2==0 else [('direct',lambda:r(selection,indices)),('mmap',old)]):
   start=time.perf_counter();a=fn();times[name].append(time.perf_counter()-start)
 print(json.dumps({'octets_par_lecture':expected.nbytes,'mediane_secondes':{k:statistics.median(v) for k,v in times.items()},'identiques':True}))
finally:r.close()
