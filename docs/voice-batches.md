# Voice generation from files

In **Mes voix → Générer depuis des fichiers**, choose a compatible voice and
select up to 20 UTF-8 `.txt` or `.md` files. Preview or remove individual files,
then add the lot to the queue. Each file produces its own WAV download, named
after the source file. Inline Drama directions and paired delivery tags remain
in the text. Markdown is passed as text; it is not rendered or stripped.

Each file must contain 1–5,000 characters; the browser also limits source files
to 64 KiB. Empty files, invalid UTF-8, unsupported extensions and binary NULs are
rejected. The entire lot is validated before any tasks are queued. A UTF-8 BOM
and surrounding whitespace are removed.

The existing single worker runs the tasks sequentially and retains normal memory
protections. Each file has an independent status, cancellation control, error,
and audio result. Failure of one task does not stop the queue. The chosen model
is captured when the batch is queued. Seeds remain independently randomized by
the existing per-task mechanism. Task history persists through the existing
task store; the voice view retains the latest 20 lots, independent of the global
recent-task limit. Files themselves are read locally in the browser; their text
is sent only to the local Studio Avatar server.

`POST /api/voix/lot` accepts:

```json
{
  "profil": "local-voice-id",
  "fichiers": [
    {"nom": "01-introduction.txt", "texte": "[amusée] Bonjour !"},
    {"nom": "02-conclusion.txt", "texte": "À bientôt."}
  ]
}
```

It returns `lot`, `ajoutees`, and the queued task IDs. `GET /api/voix` exposes
compact lot task summaries under `lots`; it omits their full script text.

Validation: `python3 -m unittest test_voix` and `node test_voix_lot.js`.
