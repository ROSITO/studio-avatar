"""Estimated speech progress, with exact native text-block boundaries."""
import re


def installer(modele, texte):
    from mlx_audio.tts.models.fish_drama3.chunking import split_text
    from balises import parle
    chunks=split_text(texte)
    weights=[max(1,len(re.sub(r'<\|[^|]*\|>','',parle(c)).split())) for c in chunks]
    total=sum(weights);original=modele._frames
    state=dict(index=0,words=0,frames=0)
    def frames(*args,**kwargs):
        index=state['index'];state['index']+=1
        if index>=len(weights):yield from original(*args,**kwargs);return
        weight=weights[index];count=0
        def log(fraction):
            percent=min(99,int(100*(state['words']+weight*fraction)/total))
            print(f'Voix progression : {percent}% · bloc {index+1}/{len(weights)}',flush=True)
        log(0)
        expected=weight*(state['frames']/state['words'] if state['words'] else 7)
        for frame in original(*args,**kwargs):
            count+=1
            if count==1 or count%16==0:log(min(.9,count/max(1,expected)))
            yield frame
        log(1);state['words']+=weight;state['frames']+=count
    modele._frames=frames
