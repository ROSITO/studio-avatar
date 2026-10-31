# Drama voice directions

Studio Avatar preserves plain inline emotion tags for Drama, including tags also
used to select video gestures (`[curious]`, `[excited]`, `[serious]`, etc.). Other
voice engines still receive spoken text with bracket cues removed. The legacy
`[voice:excited]` spelling remains supported. Paragraph breaks are preserved.

The local runtime still performs its native text splitting, including protection
of paired tags. In monologues, a cue stranded at the end of a chunk moves to the
following text. The most recent delivery direction is repeated at subsequent
chunk boundaries until a new direction replaces it. Point events such as laughs,
sighs and pauses are never repeated. Explicit multi-speaker scripts retain native
splitting; automatic per-speaker direction propagation is not implemented.

Streaming and file output explicitly use the same sampling recipe: temperature
1.0, top-p 0.9, top-k 30, matching the published Fish Audio Drama 3 serving example:
https://huggingface.co/fishaudio/drama-3
This is a sampling adjustment, not a verified quality or speed improvement.

Exact reference and causal-prefix caches remain enabled. Generated takes are not
cached or substituted. Memory limits and the system reserve are unchanged. More
expressive directions can produce longer audio and therefore longer generation.

Validation: `python3 -m unittest test_drama_direction test_balises test_voix`.
With the optional voice runtime, also run `test_drama_progression`,
`test_drama_vitesse` and `test_drama_cache` to check native splitting, progress
boundaries, exact cache reuse and memory-pressure eviction.

## Feeding the GPU

Routed expert matrix multiplication already runs on Metal. A CPU cache now
defaults to 512 MiB (`STUDIO_DRAMA_EXPERT_CACHE_MB=0` disables it), additionally
limited to one sixteenth of the worker memory budget. It retains a stable subset
of expert rows rather than evicting all previous layers on every decode frame.
This avoids repeated disk reads for retained experts without changing their
values. The existing pressure guard releases the cache when needed. This does
not change an already running worker; the next generation loads the new policy.
No end-to-end speedup has yet been measured for this default.
