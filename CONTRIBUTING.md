# Contributing

Thank you for helping improve Studio Avatar. Both English and French contributions
are welcome. Follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Before making a change

Search existing issues and pull requests. Use the bug or feature template for a
reproducible problem or proposal; use Discussions for setup questions. Discuss
large architectural changes before investing in an implementation.

## Local development

1. Fork the repository and create a focused branch from `main`.
2. Install Python 3.10+ and FFmpeg (`ffmpeg` and `ffprobe` on PATH).
3. Start the server with `python3 studio.py`. Engine setup is optional for UI,
   persistence, and synthetic-media tests; see README.md for real generation.
4. Run `python3 -m unittest discover -p 'test_*.py' -v` and
   `python3 -m py_compile studio.py projets.py lancer_musetalk15.py visage.py`.
5. If changing the UI, verify the affected flow at desktop and mobile widths.

## Pull requests

Explain the user-visible problem, the resulting behavior, and how it was tested.
Keep changes focused. Add meaningful regression coverage for timeline persistence,
job recovery, dependency invalidation, or assembly changes. Never replace independent
clips with a pipeline that regenerates the whole project for a local edit.

Do not commit portraits, voices, recordings, project JSON, logs, model weights,
credentials, absolute personal paths, or screenshots containing personal data.
Use temporary synthetic fixtures. Check `git diff --cached` before pushing.

Use the pull request template. Maintainers may request changes and merge after
review and passing checks. Contributions are accepted under the repository's MIT
license; submit only code and assets you have the right to contribute.

## Security

Report vulnerabilities privately using SECURITY.md rather than a public issue.
