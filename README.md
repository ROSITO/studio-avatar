# Studio Avatar

[![CI](https://github.com/ROSITO/studio-avatar/actions/workflows/ci.yml/badge.svg)](https://github.com/ROSITO/studio-avatar/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-ffc629.svg)](LICENSE)
[![Community standards](https://img.shields.io/badge/community-standards-blue.svg)](https://github.com/ROSITO/studio-avatar/community)

A local avatar-video studio with an editable, persistent timeline. Start with a photo
and a tagged script, generate individual LTX mini-clips, then connect their poses
with LTX transitions. Assemble and lip-sync only when you are ready.

**Experimental software.** The interface is currently in French. The generation
recipe targets Apple Silicon and separately installed LTX-2-MLX, MuseTalk 1.5, and
an optional VoiceStudio-compatible speech API. A complete GPU render is not part
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
Explicit assembly + MuseTalk lip-sync -> downloadable video
```

- One recognized TAG opens one block, even if it contains several sentences.
- Edit a block's text, intention, LTX direction, duration, and seed.
- Regenerate only that block. Other clips and completed speech audio are retained.
- Only the adjacent transitions become stale; distant transitions remain valid.
- A transition joins the last **retained** frame of one clip to the first frame of
  the next. It does not return to the original photo.
- Move or remove blocks and regenerate only the missing elements.
- Projects and individual outputs persist on disk. A failed LTX task retains
  completed audio; completed elements are reused after a restart.

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

Existing raw clips and audio are preserved. Older append-style bridges are marked
stale and must be regenerated, because their starting anchor is different. Previous
exports remain accessible but are labeled outdated. The preview monitor and final
export share the same edit-decision code in `montage.py`.

Imported audio is initially split in proportion to script length, not by forced
alignment. Adjusting a block's total duration can still trim speech or add silence;
this is separate from the integrated return, which never adds a pause. Clip-duration
edits currently accept 0.5–20 seconds.

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

1. Install an [LTX-2-MLX](https://github.com/dgrauet/ltx-2-mlx) CLI supporting `generate`, `--image`, `--distilled`,
   `--low-ram`, and the other flags used by `studio.ltx`.
2. Put the expected LTX weights in `STUDIO_MODELS_DIR/ltx-2.3-q4/`.
3. Install [MuseTalk](https://github.com/TMElyralab/MuseTalk), including its
   `musetalkV15`, `sd-vae`, Whisper, and face-processing models. Configure its
   checkout and Python interpreter below. The local recipe was developed with the
   [musetalk-macos](https://github.com/huzp611/musetalk-macos) fork. `lancer_musetalk15.py` is a local adapter.
4. For text-to-speech, run a compatible VoiceStudio server. The expected contract
   is `GET /profiles` returning profiles with `id` and `name`, and `POST /generate`
   accepting form fields and returning a WAV (see `studio.voix`). Alternatively,
   import your own WAV/MP3 audio.

```bash
cp .env.example .env
# Edit .env with your engine/model locations, then load it:
set -a
source .env
set +a
python3 studio.py
```

`.env` is a shell configuration example, **not** automatically loaded by Python.
The default port is 8765, the default speech API is `http://127.0.0.1:3900`, and
the default model directory is `~/.cache/studio-avatar/models`. See
[.env.example](.env.example) for all supported variables.

Once configured: **Nouvelle vidéo → Créer le projet → Mes projets**. Create the
project first, generate selected clips/transitions, and finally choose
**Assembler et synchroniser**. Previous exported videos remain under **Mes vidéos**.

## Automatic generation and seeds

In a project, **Tout générer automatiquement** runs all remaining clips and
transitions, then assembles and lip-syncs the final video. It preserves ready
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
- the live VoiceStudio TTS engine catalogue and per-synthesis engine selection.

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
that a block has already generated. Voice engine packages/weights continue to be
installed and licensed by VoiceStudio; Studio Avatar lists available engines and
passes the chosen `engine` to its compatible `/generate` API. Legacy speech servers
without `/engines/tts` still work with the original speech interface.

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
assembly. LTX, MuseTalk, and speech generation are replaced by test implementations;
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
