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

Transitions currently add a configurable **silent pause** between spoken blocks
(one second by default). Imported audio is initially split in proportion to script
length, not by forced alignment. Adjusting a rendered block's duration can trim
speech or add silence. Clip-duration edits currently accept 0.5–20 seconds; long
TAG blocks need to be shortened before generating through the editor.

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

The studio orchestrates external tools; it does not install engines or download
model weights automatically. Install each engine in its own environment, obtain
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
python3 -m py_compile studio.py projets.py lancer_musetalk15.py visage.py
```

Tests create synthetic media in temporary directories and exercise real FFmpeg
assembly. LTX, MuseTalk, and speech generation are replaced by test implementations;
no model weights, personal assets, speech server, or GPU are needed. CI runs the
same suite on Python 3.10 and 3.14.

The server lives in `studio.py`, persistent timeline logic in `projets.py`, and the
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
