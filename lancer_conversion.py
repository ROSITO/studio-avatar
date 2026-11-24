"""Worker isolé : RVC, limite mémoire et sortie sans blocage natif à la fermeture."""
import os
from pathlib import Path
import runpy
import sys
import memoire

runtime, poids, index, source, sortie, pitch = sys.argv[1:]
memoire.verifier('drama3-mlx')
memoire.surveiller(12 * memoire.GIB)
os.chdir(runtime)
sys.path.insert(0, runtime)
os.environ['OMP_NUM_THREADS'] = '4'
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
import torch
torch.set_num_threads(4)
sys.argv = ['infer/cli.py','--model',poids,'--speaker-id','0','--input',source,'--output',sortie,'--index',index,'--index-rate','0.75','--pitch',pitch,'--f0-method','rmvpe','--format','wav']
code = 0
try:
    runpy.run_path(str(Path(runtime)/'infer/cli.py'), run_name='__main__')
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else 0
except BaseException:
    import traceback
    traceback.print_exc()
    code = 1
sys.stdout.flush(); sys.stderr.flush()
os._exit(code)
