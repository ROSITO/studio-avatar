"""Stage routed Drama experts from safetensors on disk, without loading whole banks."""
import json
import struct
import os
from contextvars import ContextVar
from pathlib import Path

def activer(mx,modele,dossier,lecteur=None):
    import numpy as np
    from mlx_audio.lm.models.switch_layers import QuantizedSwitchLinear,SwitchGLU
    if not mx.metal.is_available():return
    tables={}
    types={'U32':'uint32','F32':'float32','F16':'float16','BF16':'uint16'}
    for fichier in Path(dossier).glob('*.safetensors'):
        with fichier.open('rb') as f:
            taille=struct.unpack('<Q',f.read(8))[0]
            entete=json.loads(f.read(taille))
        for cle,info in entete.items():
            if '.switch_mlp.' in cle:
                tables[cle]=(fichier,types[info['dtype']],8+taille+info['data_offsets'][0],tuple(info['shape']))
    sources={}
    blocs=set()
    asynchrone=ContextVar('drama_experts_asynchrones',default=False)
    chevaucher=os.environ.get('STUDIO_DRAMA_OVERLAP','0')=='1'
    for nom,module in modele.named_modules():
        if isinstance(module,SwitchGLU):blocs.add(id(module))
        if not isinstance(module,QuantizedSwitchLinear):continue
        banques={}
        for attribut in ('weight','scales','biases'):
            valeur=module.get(attribut)
            if valeur is None:continue
            banques[attribut]=(tables[nom+'.'+attribut],valeur.dtype)
            # Preserve shapes for introspection, but discard lazy whole-bank loads.
            module[attribut]=mx.zeros(valeur.shape,dtype=valeur.dtype)
        sources[id(module)]=banques
    def calcul(self,x,indices,sorted_indices=False):
        uniques,inverse=np.unique(np.asarray(indices),return_inverse=True)
        with mx.stream(mx.cpu):
            buffers={}
            if lecteur is not None:
                copies=lecteur(sources[id(self)],uniques,id(self))
            else:
                copies={}
                for cle,(description,dtype) in sources[id(self)].items():
                    fichier,type_numpy,decalage,forme=description
                    banque=np.memmap(fichier,mode='r',dtype=type_numpy,offset=decalage,shape=forme)
                    try:copies[cle]=np.array(banque[uniques],copy=True)
                    finally:banque._mmap.close()
            for cle,copie in copies.items():
                dtype=sources[id(self)][cle][1]
                valeur=mx.array(copie)
                buffers[cle]=valeur.view(dtype) if valeur.dtype!=dtype else valeur
            mx.eval(buffers)
        with mx.stream(mx.gpu):
            routes=mx.array(inverse.reshape(indices.shape).astype(np.int32))
            resultat=mx.gather_qmm(x,buffers['weight'],buffers['scales'],buffers.get('biases'),
                rhs_indices=routes,transpose=True,group_size=self.group_size,
                bits=self.bits,mode=self.mode,sorted_indices=sorted_indices)
            if 'bias' in self:resultat=resultat+mx.expand_dims(self['bias'][indices],-2)
            if asynchrone.get():mx.async_eval(resultat)
            else:mx.eval(resultat)
        return resultat
    QuantizedSwitchLinear.__call__=calcul
    if chevaucher and blocs:
        # Keep at most one expert block outstanding. CPU disk staging for the
        # next projection may overlap Metal work already submitted in this one.
        original=SwitchGLU.__call__
        def bloc(self,*args,**kwargs):
            if id(self) not in blocs:return original(self,*args,**kwargs)
            token=asynchrone.set(True)
            try:
                result=original(self,*args,**kwargs)
                with mx.stream(mx.gpu):mx.eval(result)
                return result
            finally:asynchrone.reset(token)
        SwitchGLU.__call__=bloc
        print(f'Experts GPU : préparation chevauchée, synchronisation bornée à {len(blocs)} blocs',flush=True)
    from mlx_audio.tts.models.fish_drama3 import drama3
    drama3.PREFILL_CHUNK=64
    mx.set_default_device(mx.gpu)
    mx.set_wired_limit(0)
