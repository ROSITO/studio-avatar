# Studio Avatar

[![CI](https://github.com/ROSITO/studio-avatar/actions/workflows/ci.yml/badge.svg)](https://github.com/ROSITO/studio-avatar/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-ffc629.svg)](LICENSE)
[![Community standards](https://img.shields.io/badge/community-standards-blue.svg)](https://github.com/ROSITO/studio-avatar/community)

A local avatar-video studio with an editable, persistent timeline. Start with a photo
and a tagged script, generate individual LTX mini-clips, then connect their poses
with LTX transitions. Assemble only when you are ready.

**Experimental software.** The interface is currently in French. The generation
recipe targets Apple Silicon and separately installed LTX-2-MLX, optionally MuseTalk
1.5, and integrated MLX speech synthesis. A complete GPU render is not part
of automated testing. No pretrained models, personal projects, voices, portraits,
example videos, or private configuration are distributed.

## How the timeline works

```text
Photo + tagged script
        |
        v
[curious] clip A -> LTX transition A–B -> [excited] clip B -> transition B–C -> clip C
        |
        v
Explicit assembly (+ MuseTalk lip-sync in that engine) -> downloadable video
```

### Block engines

Each project chooses its engine in the timeline (**Moteur des blocs**):

- **a2v talking video** (default for new projects): `ltx-2-mlx a2v` animates the
  photo directly from the block's speech, so lips follow the voice. Transitions are
  generated the same way with the speech they carry. No MuseTalk pass at export.
  a2v needs audio covering the whole clip (8k+1 frames at 24 fps): each speech
  slice is automatically padded with silence (+0.2 s margin).
- **Closed-mouth gestures + MuseTalk 1.5**: silent LTX gestures, then MuseTalk
  lip-sync at export. Projects created before a2v keep this engine.

Switching engine marks every clip and transition stale (audio is kept).

**Face check** (optional, off by default): after each clip, `visage.py` measures how
far the face moves (share of face width). Above 0.2 (tilted or turned head), the
clip is redone with the next seed, up to 3 attempts; the steadiest one is kept.
Requires OpenCV in `STUDIO_CV_PYTHON`.

- One recognized TAG opens one block, even if it contains several sentences.
  Long blocks are split at sentence boundaries into blocks of at most about
  6 seconds (estimated at 14 characters per second), because the face drifts
  over longer LTX passes. A single sentence is never cut.
- Edit a block's text, intention, LTX direction, duration, and seed.
- Regenerate only that block. Other clips and completed speech audio are retained.
- Only the adjacent transitions become stale; distant transitions remain valid.
- A transition joins the last **retained** frame of one clip to the first frame of
  the next. It does not return to the original photo.
- Move or remove blocks and regenerate only the missing elements.
- Projects and individual outputs persist on disk. A failed LTX task retains
  completed audio; completed elements are reused after a restart.

Gestures use the face and head only (nod, raised eyebrows, smile, lean, lowered
eyes); hands rest still on the lap in every engine. Hand gestures such as open palms
are excluded because the following transition must bring the hands back, which is
the hardest case for a join.

Recognized tags include `[neutral]`, `[curious]`, `[excited]`, `[thoughtful]`,
`[serious]`, and `[warm]`, with aliases defined in `studio.py`. Unknown tags do not
start a new block.

Returns to the shared start pose are **integrated into the end of the preceding
spoken block**, not appended as silent pauses. A 0.5-second return replaces the
last 0.5 seconds of that block's raw gesture; its speech continues over those
images. The next block starts immediately. Total duration remains the speech
length (rounded cumulatively to the nearest 24 fps frame).

The LTX bridge starts from the last retained frame before the replaced tail and
ends at the following rush's first frame. No end-pose constraint is applied to the
whole gesture generation. New returns default to 0.5 seconds; saved user durations
are retained and bounded so at least one original gesture frame remains.

**Join check.** LTX does not always reach the imposed end frame: it may paste it
as the very last image, which shows as a cut. After each transition, the studio
measures the visible jumps (clip → transition and transition → next clip, on
96×150 greyscale thumbnails). Above `SEUIL_PONT` (4.0; normal speech motion is
2–3.5), the transition is regenerated with the next seed, up to 3 attempts, and the
smoothest one is kept (`ecart` in the project file).

Existing raw clips and audio are preserved. Older append-style bridges are marked
stale and must be regenerated, because their starting anchor is different. Previous
exports remain accessible but are labeled outdated. The preview monitor and final
export share the same edit-decision code in `montage.py`.

Imported audio is initially split in proportion to script length, not by forced
alignment. Adjusting a block's total duration can still trim speech or add silence;
this is separate from the integrated return, which never adds a pause. Clip-duration
edits currently accept 0.5–20 seconds.

## Create an avatar (FLUX)

The **Créer un avatar** tab generates the avatar photo itself with
[mflux](https://github.com/mflux-community/mflux): a description, up to 4 optional
reference photos (face, outfit, setting, style) or an existing avatar as a starting
point, and 1–4 variants per run. The animation pose is imposed (seated, facing the
camera, head upright, mouth closed, hands resting low). **Utiliser comme avatar**
copies a result into `sources/`.

- **FLUX.2 Klein 4B** (default): Apache 2.0, distilled recipe (4 steps, 8-bit),
  about 40 s per 768×1200 image on an M3 Pro, ~13 GB peak memory.
- **FLUX 3 Image Klein MLX 8-bit** (option, **Modèles** page): FLUX Kommunity
  License, **non-commercial**; a monetized video requires a BFL license. Slower.

Set `STUDIO_MFLUX_BIN` to the folder holding `mflux-generate-flux2[-edit]` and
`mflux-generate-flux3[-edit]`. Weights already installed elsewhere are detected via
`STUDIO_IMAGE_MODELS_DIR` (`flux2/klein-4b`, `flux3/klein-mlx-8bit`).

## Start the interface

Requirements: Python 3.10+, `ffmpeg`, and `ffprobe` on your PATH. The web server
uses only the Python standard library; opening the interface requires no models.

```bash
git clone https://github.com/ROSITO/studio-avatar.git
cd studio-avatar
python3 studio.py
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). On macOS you can also run
`lancer.command`. Install FFmpeg using your system package manager (for example,
`brew install ffmpeg` on macOS or `sudo apt-get install ffmpeg` on Ubuntu).

## Configure generation engines

The studio orchestrates external tools. Install the engines separately; model
weights can then be downloaded explicitly from the **Modèles** page. Install each engine in its own environment, obtain
its required models, and follow its upstream setup instructions and licenses.

1. Install an [LTX-2-MLX](https://github.com/dgrauet/ltx-2-mlx) CLI supporting `generate`, `a2v`, `--image`, `--distilled`,
   `--low-ram`, and the other flags used by `studio.ltx`.
2. Put the expected LTX weights in `STUDIO_MODELS_DIR/ltx-2.3-q4/`.
3. Optional (closed-mouth engine only): install [MuseTalk](https://github.com/TMElyralab/MuseTalk), including its
   `musetalkV15`, `sd-vae`, Whisper, and face-processing models. Configure its
   checkout and Python interpreter below. The local recipe was developed with the
   [musetalk-macos](https://github.com/huzp611/musetalk-macos) fork. `lancer_musetalk15.py` is a local adapter.
4. For integrated text-to-speech on Apple Silicon, run `python3 installer_voix.py`
   (Python 3.11+ recommended). This creates a separate `.venv-voix` runtime.
   In **Modèles → Synthèse vocale intégrée**, verify the download size, then install
   **Qwen3-TTS 0.6B MLX** or **Drama 3 MLX**. Weights use `STUDIO_MODELS_DIR`,
   including an external SSD when configured. Import audio instead on other platforms.
5. Open **Mes voix**. Import a 2–60 second reference, enter its exact transcript,
   name the profile and generate a test take. The same profile is available when
   creating a video. VoiceStudio is not needed. **Importer mes profils VoiceStudio**
   is an optional one-time migration while its local server is available; it copies
   references/transcripts and preserves old project profile IDs. Different speech
   models can change the voice's sound. Existing audio is never regenerated implicitly.

```bash
cp .env.example .env
# Edit .env with your engine/model locations, then load it:
set -a
source .env
set +a
python3 studio.py
```

`.env` is a shell configuration example, **not** automatically loaded by Python.
The default port is 8765. The optional VoiceStudio migration URL is `http://127.0.0.1:3900`, and
the default model directory is `~/.cache/studio-avatar/models`. See
[.env.example](.env.example) for all supported variables.

Once configured: **Nouvelle vidéo → Créer le projet → Mes projets**. Create the
project first, generate selected clips/transitions, and finally choose
**Assembler** (**Assembler et synchroniser** with MuseTalk). Previous exported videos remain under **Mes vidéos**.

## Automatic generation and seeds

In a project, **Tout générer automatiquement** runs all remaining clips and
transitions, then assembles the final video (with MuseTalk lip-sync in that engine). It preserves ready
rushes. A single resumable orchestration task tracks the sequence, stops on the
first failure/cancellation, and never leaves dependent export jobs running after
a failure. Restarting automatic generation reuses completed outputs and audio.
The individual generation buttons and explicit export remain available.

Seeds are random by default for clips and transitions (including existing projects
without an explicit seed mode). Each new inference task draws a seed and persists
it before running the engine. Resuming that task keeps the draw; a new regeneration
draws again. Choose **Fixer une seed manuellement** to enter a reproducible integer
from 0 to 2147483647. Manual seeds never increment on regeneration. The last used
seed remains visible for inspection and copying into manual mode. Advanced movement
generation also defaults to random seeds.

## Rush preview monitor

Above the project timeline, **Moniteur du montage** builds a lightweight CPU-only
preview from the existing rushes. It uses the same retained frames, transition
anchor trimming, timing and available block audio as the final export. It never
runs LTX or MuseTalk and does not replace the final export.

- **Prévisualiser la timeline** reads the contiguous ready portion from the start,
  stopping before the first missing or stale element. Partial previews are labeled.
- Select a ready transition and choose **Revoir cette jonction** to preview only
  the preceding clip, the bridge and the following clip.
- Enable **Lecture en boucle** to review a join repeatedly. Native playback,
  seeking and fullscreen controls are available; the playing element is highlighted.
- Changing the project marks an older preview as outdated. Rebuild explicitly;
  previews are cached by source versions and durations, without regenerating rushes.

The monitor combines video and available speech audio at reduced resolution, with
no final lip-sync. Preview work has its own CPU process and never replaces the
GPU worker's process handle. Cached preview media stays in the ignored local
`sequences/` folder. Its logic is in `apercus.py`; tests use synthetic media.

## Model catalogue and downloads

The **Modèles** page provides:

- LTX-2.3 Q4, Q8, and BF16 packs for the current distilled recipe;
- the shared Gemma 3 12B 4-bit text encoder;
- MuseTalk 1.5 weights with SD-VAE, Whisper, DWPose, and face-parsing components;
- discovery of installed packs and imports of existing local LTX-2.3 folders;
- persisted selection for subsequent jobs, without rebuilding existing clips;
- integrated Qwen3-TTS and Fish Audio Drama 3 MLX weights and per-task selection.

Click **Vérifier la taille** to resolve upstream manifests and show the actual bytes
for the files used by this recipe. Click **Télécharger / reprendre** to download.
Files are fetched at pinned repository revisions, streamed to `.part` files,
verified against SHA-256 or Git blob hashes, then renamed atomically. Transfers
support cancellation and resumption; interrupted transfers are not restarted
without an explicit request. Available disk space is checked before downloading.
No remote Python code is downloaded or executed by the manager.

Packs are stored in `STUDIO_MODELS_DIR/catalogue/`. The previous
`STUDIO_MODELS_DIR/ltx-2.3-q4` layout and an existing shared Gemma HF cache are
automatically detected. MuseTalk components are stored in
`STUDIO_MUSETALK_ROOT/models/` because the upstream adapter expects this layout.
The FaceAlignment package may separately obtain its detector/landmark checkpoints
through its own PyTorch cache; engine dependencies are not installed by this page.

Review the upstream license links before installing. Restricted repositories may
require accepting their terms on Hugging Face and setting `HF_TOKEN` in the server
environment. The token is never returned to the UI or stored in Studio Avatar's
preferences. It is stripped from cross-host redirects.

Model switches and weight installations are blocked while generation jobs are
pending or running. Each timeline job records its selection when queued. Existing
clips and audio are retained: changing the voice engine does not replace audio
that a block has already generated. Speech runs in an isolated subprocess and releases
its memory before video generation. No output fade, crossfade or silence trimming is
applied. Cloned profiles, requests and synthetic-audio metadata stay private. A
cancelled/failed synthesis cannot replace an existing take. Weight loading is offline;
only an explicit catalogue download can fetch new model files.

Drama 3 uses the **community MLX conversion**, not the original CUDA runner and not
PyTorch MPS. Its published memory figures are indicative; verify performance on your
machine before a long video. Its Fish Audio Community License differs from this
application's MIT license. Qwen3-TTS weights use Apache 2.0. Runtime dependencies and
models keep their upstream licenses. No VoiceStudio AGPL implementation is vendored.
See [Drama 3 MLX](https://huggingface.co/mlx-community/fish-audio-drama-3-4bit),
[Qwen3-TTS MLX](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit)
and [MLX Audio](https://github.com/Blaizzy/mlx-audio).


Model choices, imported absolute paths, download manifests, and progress are private
runtime state (`modeles.json` and `.modeles-*.json`), excluded from Git. The tests
exercise resumption, ignored HTTP Range requests, corruption, cancellation, disk
space checks, selection persistence, import validation, and redirect token handling
without downloading large weights.

## Data and local security

Runtime directories (`sources`, `audios`, `clips`, `ponts`, `sequences`, `lipsync`,
`videos`, `projets`, `taches`) and `taches.json` are created locally and ignored by
Git. Removing a timeline block does not delete its old media files.

The server binds only to `127.0.0.1`. It has no authentication and supports file
uploads and GPU jobs. Do not expose it to a LAN, the public internet, or an
untrusted reverse proxy. Model engines have their own network and privacy
behavior. Only use images and voices you have permission to use.

## Development and tests

```bash
python3 -m unittest discover -p 'test_*.py' -v
python3 -m py_compile studio.py projets.py modeles.py lancer_musetalk15.py visage.py
```

Tests create synthetic media in temporary directories and exercise real FFmpeg
assembly. LTX, MuseTalk, mflux, and speech generation are replaced by test implementations;
no model weights, personal assets, speech server, or GPU are needed. CI runs the
same suite on Python 3.10 and 3.14.

The server lives in `studio.py`, persistent timeline logic in `projets.py`,
shared video/audio cuts in `montage.py`, the model manager in
`modeles.py`, and the
French web UI in `index.html`. Legacy library-based generation remains available
for compatibility, while the new creation flow uses persistent TAG projects.

## Community

Contributions and reproducible bug reports are welcome. Read
[CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md),
[SECURITY.md](SECURITY.md), and [SUPPORT.md](SUPPORT.md).

- [Report a bug or propose a feature](https://github.com/ROSITO/studio-avatar/issues/new/choose)
- [Ask a usage question](https://github.com/ROSITO/studio-avatar/discussions)
- [Community standards](https://github.com/ROSITO/studio-avatar/community)

## License and acknowledgements

Studio Avatar's code is released under the [MIT License](LICENSE). External engines,
model weights, libraries, and user-supplied media retain their own licenses and are
not included or relicensed by this repository. MuseTalk and the LTX ecosystem make
the local generation workflow possible.

### Raccords adaptés aux poses

Les raccords analysent des miniatures du corps dans la fin du rush et les comparent à la première image du suivant. Ce score visuel est une approximation, pas une détection du squelette. Le point de coupe et la durée sont choisis ensemble pour réduire le déplacement et éviter une coupure pendant un geste rapide. La durée saisie est une préférence ; la durée retenue peut atteindre 1,3 seconde. Une coupe directe évite LTX si les images sont presque identiques. Les retours LTX utilisent leur cadence native de 24 images/s, sans compression temporelle. La voix reste continue et la durée totale ne change pas. Les anciens raccords sont à régénérer ; les rushs sont conservés.

### Preserve voice identity when migrating

An audio reference alone does not preserve the sound of a voice when switching
TTS models. Imported profiles record their original engine. Synthesis rejects a
mismatched selected engine instead of silently producing a different voice.
For original OmniVoice profiles, install the independent upstream runtime with
`python3.12 installer_voix.py --moteur omnivoice`, then select **OmniVoice**.
Existing complete `k2-fsa/OmniVoice` snapshots under the configured external
Hugging Face cache are reused without copying/downloading their weights. The
adapter uses MPS on Apple Silicon, 16 diffusion steps, guidance 2, and raw output.
It imports upstream `omnivoice`, never VoiceStudio's package or HTTP synthesis API.
OmniVoice code is Apache 2.0; its model weights are CC-BY-NC. See the
[upstream model card](https://huggingface.co/k2-fsa/OmniVoice). A listening comparison
is still needed; using the same model does not guarantee bit-identical takes.

### Voice memory protection

Speech has a default 12 GiB budget, never above half of physical RAM. Set
`STUDIO_TTS_MAX_RAM_GB` to lower it. Admission checks run before model loading:
standard model estimates must fit the budget, macOS memory pressure must be normal, and
available RAM must cover the estimate plus a 4 GiB reserve. Drama 3's conservative
28 GiB estimate is informational: Drama 3 is admitted as a bounded experiment,
not rejected solely for its model size. It retains the configured budget instead of shrinking it to a snapshot of
currently available memory. Admission requires at least 4 GiB currently available
and a non-critical macOS memory pressure level; the live watchdog retains its
pressure and reserve checks. At least 2 GiB must be configured for the trial. A bounded trial may stop before producing
audio if the model cannot run within the available memory.
The MLX cache is limited to 256 MiB; MPS synthesis configures PyTorch's allocator
fraction. An isolated watchdog checks resident memory and macOS pressure every
0.5 seconds; the MLX worker also checks active + cached Metal allocations and
exits with a visible protection error when over budget. This is a best-effort
protection, not an OS-enforced memory sandbox: MLX's memory limit alone is a
[guideline](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.set_memory_limit.html).
No high-memory inference is run in the automated tests. These guards apply to
integrated speech workers; external LTX and image engines have separate allocators.

Drama trials also have an external watchdog in the server, independent of the
inference interpreter's GIL. On macOS it samples `proc_pid_rusage` resident memory
and physical footprint every 100 ms and kills only the inference child if its
budget is exceeded, macOS reports critical memory pressure, or a memory warning
coincides with less than 4 GiB available. A moderate warning alone does not stop
a trial that still has its reserve. Unknown measurement fails
closed. MLX's allocation limit remains a guideline, not a hard OS quota. Drama's
virtual mapped weight size is not used as a resident-memory test. Drama uses the
CPU for lazy model loading, then stages only routed experts directly from
safetensors on the model disk into temporary GPU buffers. Source mappings are closed
after each staging copy. The codec and dense operations run on Metal;
expert banks are never eagerly loaded as a whole. Prefill uses 64-frame batches.
This trades disk bandwidth for a smaller working set. The audio
frame budget is 256 frames for short takes and 1024 for longer text. Longer
takes use the causal audio decoder in one-second chunks to avoid a large
end-of-take allocation. The same memory watchdogs remain active. No production app is closed to make room.

### Drama voice directions

The text editor, timeline blocks and voice workshop include Soupir `[sighs]`,
Rire `[laughs]` and Chuchoter `[whispers]` buttons when Drama 3 is selected.
Visual TAGs such as `[curious]` open a video block; vocal directions remain inside
that block and are passed to Drama without creating another rush. Additional
Drama directions can be entered inline. Use `[voice:curious]` to request a vocal
direction whose name also exists as a visual TAG; it is sent as `[curious]`.
The interpretation of a direction depends on Drama; laughter and sighs were
validated in a local Hélie trial. Whispering is supported by the upstream runner.

OmniVoice and Qwen receive the spoken text with all bracketed directions removed.
Imported audio is unchanged. Duration estimates ignore directions; generated
audio determines the actual duration. Editing a block's vocal directions
invalidates only that block's voice/video and the affected joins.

### Reuse Drama reference preparation

Drama saves the reference-only attention and linear states losslessly in
`<model directory>/.studio-avatar-cache` on the model disk. The requested speech
is always generated anew. The cache key includes reference audio, transcript,
model file sizes/mtimes, runtime versions and the offload adapter. Encoded
reference tokens must also match before a saved prefix is reused. Invalid or
unreadable entries fall back to ordinary preparation. Cache entries contain
private voice data and must not be published.

The inference process still exits after every take, so its GPU memory is released
before LTX runs. Cache storage is limited to 2 GiB (old entries are evicted). Set
`STUDIO_DRAMA_CACHE=0` on the server to disable reuse. `/api/voix/essai` accepts an
optional integer `seed` for reproducible comparisons; omitted seeds remain random.

Measured on a 36 GiB Apple Silicon Mac with the same 2.41-second tagged utterance
and seed: first take **492.23 s**, reused-reference take **135.83 s** (**3.62×**).
Both decoded PCM streams matched the previously validated take exactly. The
reference prefix occupied about **79 MiB** on the model disk. This measurement
applies to reuse of the same reference; a new or changed reference still needs
one full preparation. Memory admission checks and both inference watchdogs remain
active.


### Transférer une performance filmée (expérimental)

La page **À partir d’une vidéo** accepte une vidéo MP4/MOV/WebM et une photo
existante de l’avatar. Choisissez un extrait de **1 à 3 secondes**, décrivez
l’apparence et le décor de la photo, puis lancez le transfert. Le son original
peut être conservé. Les résultats et les journaux restent accessibles dans cette
page ; la vidéo exportée apparaît aussi dans Mes vidéos.

Les noyaux MPS, un petit transformer avec offload et un pipeline miniature
avec export MP4 ont été exécutés sur Apple Silicon. La validation des
paramètres des poids complets est séparée de la validation visuelle.

Ce premier mode utilise **Wan-Animate-2** : il anime le personnage dans le décor
de sa photo. Il ne propose pas encore le remplacement localisé du corps dans
le décor exact de la vidéo, ni un changement de voix. La fidélité des mains,
des expressions et de la bouche doit être évaluée sur chaque prise.

Installation Apple Silicon, dans un environnement isolé :

```sh
python3.13 installer_animation.py
```

Puis, dans **Modèles → Transfert de performance**, vérifiez la taille et
 téléchargez Wan-Animate-2 (environ 46 Go). Le répertoire configuré par
`STUDIO_MODELS_DIR` reçoit les poids et le dossier temporaire d’offload.
Prévoir **2 Go libres supplémentaires** pour les fichiers temporaires.
Les couches sont indexées dans les safetensors originaux, sans dupliquer le modèle.
Aucun téléchargement de poids n’est effectué pendant une génération.

L’intégration Diffusers repose sur la [proposition #14412](https://github.com/huggingface/diffusers/pull/14412),
encore non fusionnée lors de l’intégration, fixée à la révision
`14f482c30c91021cc0e363a0a17a115b44972aee` du contributeur `kelseyee/diffusers`.
`adapter_animation.py` adapte uniquement les deux fichiers de cet environnement
isolé : lecture vidéo OpenCV, RoPE réel FP32 et attention SDPA découpée,
sans CUDA, Flash Attention ni Triton. Ces modifications ne rendent pas le
port officiellement pris en charge par Wan ou Diffusers.

Les couches sont chargées depuis le disque plutôt que de placer tout le modèle
en RAM. Le dictionnaire UMT5 lit uniquement les lignes correspondant aux
tokens du texte ; les embeddings ne sont pas intégralement chargés en mémoire. Le budget par défaut est **12 Gio**, plafonné à la moitié de la mémoire
physique. Le plafond n’est pas réduit à partir d’une estimation instantanée de
la mémoire disponible. Un essai est refusé s’il reste moins de 4 Gio disponibles
ou si la pression mémoire est critique. Le mode normal demande un plafond
configuré d’au moins 10 Gio. Un superviseur extérieur au
processus de génération l’arrête si le budget ou la pression mémoire dépasse
les limites. La limite MPS seule ne constitue pas une garantie système.
La conversion FP32 des couches à la demande et l’offload rendent les essais
potentiellement très lents.
Les tests de noyaux et du petit transformer ne valident pas la qualité d’un
rendu avec les poids complets. Un diagnostic réel d’une seconde, une étape,
a été exporté sur MPS à résolution minimale : pic physique 2,92 Gio, environ
6 min 8 s. Ce résultat valide le parcours technique, pas la qualité visuelle
des rendus normaux à 40 étapes.

Variables facultatives : `STUDIO_ANIMATION_PYTHON` et
`STUDIO_ANIMATION_MAX_RAM_GB`. Pour lancer les tests natifs :

```sh
.venv-animation/bin/python -m unittest test_animation -v
```

Sources : [projet officiel](https://github.com/Wan-Video/Wan-Animate-2),
[poids Diffusers](https://huggingface.co/Wan-AI/Wan2.2-Animate-2-14B-Diffusers).
Les vidéos importées (`performances/`), références, résultats et poids ne sont
jamais inclus dans le dépôt public.

Le point d’entrée développeur `POST /api/animation/diagnostic` utilise le même
format que `/api/animation`, mais une seule étape et une résolution réduite.
Son budget minimal est de 2 Gio, toujours avec une réserve système de 4 Gio et
le superviseur. Il sert à vérifier le moteur complet, pas à évaluer la qualité ;
les tâches et résultats portent explicitement cette mention.


Le budget vocal par défaut est également de **12 Gio**
(`STUDIO_TTS_MAX_RAM_GB`, plafond maximal : moitié de la RAM physique).
Drama conserve ce plafond configuré au lieu de le réduire à l’estimation de
mémoire disponible moins 4 Gio. L’admission refuse moins de 4 Gio disponibles
ou une pression critique ; le superviseur extérieur conserve ses arrêts sur
empreinte excessive et pression macOS. La limite transmise au processus enfant
reste la même, même si l’estimation de mémoire disponible fluctue.


Les erreurs de protection distinguent désormais le plafond du moteur et la
pression mémoire **globale** de macOS, en indiquant l’empreinte et le plafond.
Les prises longues Drama enregistrent après chaque portion décodée un snapshot
WAV float32 atomique, lisible même après un arrêt forcé. En cas d’échec ou
d’annulation, l’audio sauvegardé est conservé séparément, marqué **incomplet**
et accessible dans Mes voix. Il ne remplace jamais une prise complète existante
et ne signifie pas que la génération peut reprendre automatiquement à cet endroit.
Les anciennes prises interrompues avant cette correction n’ont pas de snapshot
récupérable.

### Drama expert reads and repeated context

Drama keeps its large expert banks on disk. By default, selected rows are now
read directly into bounded NumPy buffers using positional file reads, with file
descriptors reused throughout the worker. This avoids mapping entire banks and
the previous extra NumPy copy. It does not preload the model, raise the worker's
memory ceiling, or change routing, quantization, speech directions, or seeds.
`STUDIO_DRAMA_DIRECT_READ=0` restores the temporary-mapping reader for comparison.

Repeated first-turn context is reused only when every prefix frame matches,
including the teacher-forcing lookahead. Snapshots are limited to 256 MiB.
`STUDIO_DRAMA_CONTEXT_CACHE=0` disables this optimization. A local real-model
prefill benchmark measured 191.72 s cold versus 48.64 s with reuse, with identical
hidden states and cache states. This is a preparation benchmark, **not** an
end-to-end speech speedup claim. The normal serialized task queue and memory
supervisor also apply to diagnostic measurements.

The optional CPU expert-row cache remains **off by default**. In one local
same-text/same-seed trial, a 768 MiB cache reduced reads from 33.10 to 22.67 GiB
but increased total time from 167.99 to 198.71 s. For controlled experiments only,
`STUDIO_DRAMA_EXPERT_CACHE_MB` accepts 0–1024 MiB and is additionally capped at
one sixteenth of the worker budget. Memory pressure clears cached rows.

The direct reader passed exact row and FP32/BF16 quantized-kernel comparisons.
A small warm-file microbenchmark measured 0.56 ms versus 1.01 ms per 4 MiB read;
this does not predict full-generation time under memory pressure. Changes apply
to newly started workers; an active generation is never restarted to apply them.
