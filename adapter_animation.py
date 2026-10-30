"""Apply reviewed, fail-closed compatibility edits to a pinned isolated runtime."""
from pathlib import Path
import importlib.util

REVISION='14f482c30c91021cc0e363a0a17a115b44972aee'
MARKER='# Studio Avatar MPS adapter v1'


def adapter():
    spec=importlib.util.find_spec('diffusers')
    if not spec or not spec.origin:raise RuntimeError('Diffusers absent.')
    root=Path(spec.origin).parent
    transformer=root/'models/transformers/transformer_wan_animate_2.py'
    pipeline=root/'pipelines/wan/pipeline_wan_animate_2.py'
    for p in (transformer,pipeline):
        s=p.read_text()
        if MARKER in s:continue
        s=s.replace('import inspect','from contextlib import nullcontext\nimport inspect') if p==pipeline else 'from contextlib import nullcontext\n'+s
        s=s.replace('torch.amp.autocast(device_type="cuda", dtype=torch.float32)', 'nullcontext()')
        s=s.replace('torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16)', 'nullcontext()')
        s=s.replace('torch.amp.autocast(device_type="cuda", dtype=dtype)', 'nullcontext()')
        if p==transformer:
            if s.count('device = self.patch_embedding.weight.device')!=2:raise RuntimeError('Version transformer inattendue.')
            s=s.replace('device = self.patch_embedding.weight.device','device = torch.device("mps")')
            s+='\n'+MARKER+'\nfrom animation_mps import rope_params, rope_apply, sinusoidal_embedding_1d, create_block_mask, flash_attention, flex_attention\n'
        else:
            a=s.index('        import decord\n');b=s.index('        cond_images_np = []',a)
            s=s[:a]+'''        from animation_mps import lire_video
        all_frames, video_fps = lire_video(driving_video)
        frame_num = len(all_frames)
        target_num = int(frame_num / video_fps * fps)
        idxs = get_frame_indices(frame_num, video_fps, target_num, fps)
        frames_np = all_frames[idxs]

'''+s[b:]
            s=s.replace('generator = torch.Generator(device=device)', 'generator = torch.Generator(device="cpu")')
            s=s.replace('noise = torch.randn(', 'noise = randn_cpu(')
            s+='\n'+MARKER+'\nfrom animation_mps import randn_cpu\n'
        # Avoid partial edits on an unexpected upstream syntax.
        compile(s,str(p),'exec');p.write_text(s)


if __name__=='__main__':adapter()
