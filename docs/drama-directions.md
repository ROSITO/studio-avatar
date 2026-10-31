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

Routed expert matrix multiplication already runs on Metal. The CPU expert cache
defaults to a fixed 1024 MiB. Experimental adaptive mode starts at that size and
can adapt up to 4 GiB, additionally capped at one third of the worker budget and
leaving a conservative 10 GiB allowance for the model and transient buffers.
With a 12 GiB worker budget the adaptive maximum is therefore 2 GiB. Every second
it checks actual process footprint and system memory.
It grows by at most 256 MiB per check, retaining two GiB of worker headroom and
six GiB of available system memory. It can shrink below its initial size or clear
entirely when there is insufficient headroom, then recover later. The process
watchdog and fixed total worker budget remain in force.

`STUDIO_DRAMA_ADAPTIVE_CACHE=1` enables the experiment; its default is 0.
`STUDIO_DRAMA_EXPERT_CACHE_MB` (0–1024 MiB) sets the fixed or initial cache size.
A zero fixed cache disables expert caching.

The cache retains a stable subset of expert rows between decode frames, avoiding
repeated disk reads for retained experts without changing their values. Pressure
also limits the adaptive cache to its initial size, and clears it if the existing
pressure guard considers memory unsafe. Changes apply to newly started workers;
a running generation is never restarted to apply them.

### Local comparison

A short same-text, same-reference, same-seed trial produced bit-identical audio
samples in fixed and adaptive modes (4.226 s). The initial adaptive attempt
reached a 3.5 GiB cache limit: 72.10 s total versus 60.75 s fixed, with a process
peak of 11.95 GiB versus 9.43 GiB. It reduced source bytes read by about 30%, but
did not reduce elapsed time. That growth limit is no longer admitted at 12 GiB.

After adding the conservative model allowance, a second pair measured 71.95 s
adaptive versus 69.48 s fixed, with process peaks of 10.63 and 9.23 GiB. Source
bytes read fell from 45.92 to 39.65 GiB (about 14%). This is a short local test,
not a general model benchmark; run-to-run variability is visible even between
the two fixed trials. Adaptive mode remains opt-in because no speedup was shown.

## Expert staging experiments

The expert reader avoids copying rows that a full cache would reject. When every
requested row is newly read, it also reuses the ordered read buffer instead of
stacking a second copy. `STUDIO_DRAMA_COPY_REDUCTION=0` restores the old path for
diagnostics. A short fixed-cache pair measured 81.04 versus 81.49 seconds and
process peaks of 9.77 versus 9.13 GiB. Audio samples were identical; this supports
keeping the allocation reduction, not a speech speedup claim.

Experimental `STUDIO_DRAMA_OVERLAP=1` submits routed projections asynchronously
and waits at each SwitchGLU block boundary, bounding outstanding work to one
block. Standalone projections retain synchronous evaluation. A native block test
covers duplicate routes and BF16 inputs; the full short take was bit-identical.
A warm run took 83.62 seconds, with a subsequent synchronous warm control taking
99.83 seconds. Other controls ranged around 80 seconds: this variability is too
large to establish a reliable gain. Overlap stays off by default.

Changing the staging adapter invalidates the exact reference-prefix cache. Its
first synchronous run took 228.77 seconds including 139.43 seconds rebuilding
that prefix; this cold result must not be compared with warm runs as a speedup.

A separate 16 GiB worker-budget trial allowed the adaptive cache to reach 4 GiB.
It took 114.04 seconds, read 30.44 GiB of expert source bytes, and peaked at
12.32 GiB process memory. Audio was identical. It did not justify increasing the
normal 12 GiB budget or enabling adaptive caching. These are short local trials,
not general benchmarks or proof of the individual cause of each time difference.
Native stack samples during preparation and decoding showed substantial time in
positional weight reads, supporting further investigation of the staging path.
