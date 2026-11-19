"""Progress from completed Wan layers, passes, denoising steps and segments."""
class SuiviWan:
    def __init__(self,steps,segments,layers,passes):
        self.steps=steps;self.segments=segments;self.layers=layers;self.passes=passes
        self.segment=0;self.step=0;self.pass_index=0;self.method=None
    def avant(self,method,unconditional=False):
        self.method=method
        if method=='forward_ref':self.segment+=1;self.step=0
        elif method=='forward_gen':self.pass_index=1 if unconditional else 0
    def couche(self,index):
        done=index+1
        if done%4 and done!=self.layers:return
        if self.method=='forward_ref':
            print(f'[Wan] Préparation de la référence · couche {done}/{self.layers}',flush=True);return
        if self.method!='forward_gen':return
        fraction=(self.pass_index+done/self.layers)/self.passes
        value=100*((self.segment-1)*self.steps+self.step+fraction)/(self.segments*self.steps)
        percent=min(99,round(value,1))
        print(f'Wan avancement : {percent}% · segment {self.segment}/{self.segments} · étape {self.step+1}/{self.steps} · couche {done}/{self.layers} · passe {self.pass_index+1}/{self.passes}',flush=True)
    def terminer(self,index):self.step=index+1
