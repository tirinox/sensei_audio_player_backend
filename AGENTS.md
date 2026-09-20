# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this project is

Backend / data-processing toolkit for **Sensei Audio Player** — a Japanese listening-practice app.
It turns raw lesson recordings (MP3) into a static "audio DB" consumed by a separate frontend
([sensei_audio_player_front](https://github.com/tirinox/sensei_audio_player_front)):

1. normalize volume + re-encode incoming MP3s (`lb_` prefix = "low bitrate", processed)
2. split each recording into phrases by silence detection (pydub)
3. transcribe each phrase (local OpenAI Whisper `large`, language `ja`)
4. add furigana via an LLM (OpenAI-compatible API, DeepSeek by default)
5. build a per-course `index.json`
6. rsync the audio DB to the web host

There is no server here: the output is just files (`*.mp3`, `*_segments.json`, `index.json`).
This is a personal single-developer tool — keep changes simple and pragmatic; no need for
abstractions, frameworks, or defensive layers the code doesn't already have.

## Layout

| Path | Role |
|---|---|
| `pg.py` | CLI entry point. `command_map` at the bottom maps command name → function. |
| `Makefile` | Thin wrappers around `python pg.py <cmd>`; `make help` lists them. |
| `core/config.py` | `AUDIO_SOURCE_PATH` (from `.env`, made absolute), `NORMALIZE_TO_DBFS`. |
| `core/file_man.py` | MP3 discovery, course-code selection, filename cleanup, `lb_` check. |
| `core/audio_utils.py` | Load audio, ffprobe length/bitrate, safe normalization, low-bitrate convert. |
| `core/splitter.py` | Silence-based phrase detection → `(start_ms, end_ms)` list; whole file or only a range (`detect_pieces_in_range`). `detect_silence` here is a numpy re-implementation of pydub's with identical output (tested), ~100× faster. Also `pick_cut` (where to cut a segment) and `suggest_min_silence_len`. |
| `core/speech.py` | `SpeechRecognitionWhisper` (in use) and `SpeechRecognitionGoogle` (legacy). |
| `core/process_segments.py` | `fill_text_for()` — transcribes segments lacking text, saves after each. |
| `core/segment_man.py` | `SegmentManager` — load/save/edit `<file>.mp3_segments.json` (texts, join, split, bounds, delete). |
| `core/backup.py` | Timestamped copies of segment files under `BACKUP_PATH` (outside the audio DB), list/restore. |
| `core/indexer.py` | `AudioIndexer` — builds/loads `<CODE>/index.json`. |
| `core/furigana_neural.py` | `FuriganaNeural` — LLM furigana; prompt lives here as `PROMPT_1`. |
| `core/furigana.py` | Legacy MeCab/pykakasi furigana + ruby ⇄ `[漢字](かんじ)` converters. |
| `core/tui.py` | `run_menu()` — curses picker with type-to-filter and optional timeout. |
| `core/player.py`, `core/waveform.py` | Segment playback demo, waveform PNG rendering. |
| `editor/` | Web editor (replaces the Streamlit UI). `server.py` — FastAPI app: JSON API, MP3 with Range, static files, SSE at `/api/events`. `library.py` — scans codes/files, computes per-file status (`incoming` → `unsplit` → `no_text` → `no_furigana` → `done`, `index_stale`). `jobs.py` — one worker thread + queue for slow steps; its `print()` output becomes the job log; a file with a queued/running job is read-only (HTTP 423). `pipeline.py` — job handlers: `convert` (original is moved to `BACKUP_PATH/originals/<CODE>/`, not deleted), `split`, `transcribe`, `furigana` (only segments without `original_text`), `furigana_segment`, `reindex`, and the global `upload_dry` (reindexes stale codes, then `scripts/upload.sh --dry-run`, parses what rsync would send/delete) and `upload` (accepted only right after a successful dry run, with no stale index and no other active jobs; refused when the editor's `AUDIO_SOURCE_PATH` differs from the one in `.env`, because `upload.sh` reads `.env` itself); jobs can be chained with `then`. `static/` — no-build frontend (Vue 3 + wavesurfer.js as ES modules from jsDelivr, so it needs internet). Edits (text, join, cut, delete, re-split of a file or of one segment with a preview) are done right in the request, carry the segment's `start`/`end` (409 if the file changed meanwhile), are saved at once, and the previous version goes to `core/backup.py` first (Undo/History in the UI). |
| `webui.py`, `ui/` | Legacy Streamlit UI (to be removed once the editor covers it): segment editor (edit text, join segments) + "make upload" button. |
| `scripts/upload.sh` | `sshpass` + `rsync --delete` of the audio DB to the host; `--dry-run` only lists the changes. |
| `tests/` | `pytest` tests for the pure logic (segments, splitter, backups). |
| `experiment/`, `foo.py` | Scratch scripts (VK downloaders, prompt tests). Not part of the pipeline; some need packages that aren't installed (`vk_api`, `prompt_toolkit`). |

Git-ignored and local-only: `.env`, `cred/`, `audio_db/`, `backups/`, `temp/`, `.idea/`, `waveform.png`.

## Data model

```
$AUDIO_SOURCE_PATH/
  JPLTX/                         # a course "code": any subdirectory whose name starts with "JP"
    index.json                   # built by AudioIndexer
    lb_01．色のイメージ.mp3
    lb_01．色のイメージ.mp3_segments.json
```

Segments file (`SegmentManager.VERSION = 3`):

```json
{
  "filename": "lb_01….mp3", "title": "…", "total_segments": 21, "length": 116.4, "version": 3,
  "segments": [
    {"start": 1788, "end": 4133,
     "text": "[好](す)きな[色](いろ)は…",
     "original_text": "好きな色は…"}
  ]
}
```

- `start` / `end` are **milliseconds**; segments are a list sorted by `start`.
  v2 files stored segments as a dict — `load()` still accepts them and `save()` rewrites as v3.
- `text` is what the frontend shows. After furigana it holds `[kanji](reading)` markup and the
  plain transcript is kept in `original_text`. **The presence of `original_text` is how the code
  decides a segment was already furiganated** (`all_has_original_text`), so don't add that key
  for any other purpose.
- `index.json` entries: `audio_file`, `segment_file`, `n_segments`, `length`, `title`, `digest`
  (concatenated plain text, used for search). Custom `title`s are preserved across reindex.
- These formats are a contract with the frontend repo. Changing field names or the furigana
  markup requires a matching frontend change — flag this to the user rather than doing it silently.

## Setup and commands

Python 3.10, dependencies managed with **uv** (`pyproject.toml` + `uv.lock` are the source of
truth; `requirements.txt` is stale). System requirements: `ffmpeg`/`ffprobe`, MeCab, and `sshpass`
for upload. macOS is assumed (`afplay` in `au_sep`).

```bash
uv sync                      # create/update .venv
cp example.env .env          # then fill in values
uv run python pg.py <cmd>    # or activate .venv and use `make <target>`
uv run uvicorn editor.server:app --port 8377   # web editor
uv run streamlit run webui.py                   # legacy UI
```

The Makefile calls bare `python`, so it relies on an activated venv.

| Command (`pg.py`) | Make target | What it does |
|---|---|---|
| `process_incoming` | `process-incoming` | Full pipeline for new (non-`lb_`) files: convert → split → transcribe → reindex → furiganate everything not yet furiganated. **Deletes the original MP3s.** |
| `update [file\|N]` | `update` | Re-split (asks for min pause in ms), re-transcribe and re-furiganate **one** file, overwriting its texts. |
| `furiganate` | `furiganate` | LLM furigana for one file picked from the menu. |
| `reindex` | `reindex` | Rebuild `index.json` for a code. |
| `list` | `list` | Numbered file list (the number works as the `update` argument). |
| `normalize_volumes` | — | Re-normalize loudness of every MP3 in a code in place. |
| `convert_ruby`, `cvt_seg_v3`, `waveform`, `play_demo`, `foo` | `foo` | One-off migrations / demos. |
| — | `upload` | `scripts/upload.sh` — rsync with `--delete` to the production host. |
| — | `upload-dry` | Same with `rsync -n`: lists what would be copied/deleted. Still connects to the host. |
| — | `editor` | Web editor at http://127.0.0.1:8377 (`uvicorn editor.server:app`). |
| — | `webui` | Legacy Streamlit UI. |

Environment variables (see `example.env`; it is incomplete — these are all the ones the code reads):

- `AUDIO_SOURCE_PATH` — required; `core/config.py` fails at import without it.
- `CODE` — preselects the course code and skips the curses menu, e.g. `CODE=JPLTX make reindex`.
- `BACKUP_PATH` — where segment file backups go (default `./backups`).
- `MIN_SILENCE_LEN_MS` (800), `PADDING_MS` (200), `SILENCE_THRESHOLD_DB` (-40) — splitter tuning.
- `AI_API_KEY` (required for furigana), `AI_API_URL` (default `https://api.deepseek.com`),
  `AI_API_MODEL` (default `deepseek-chat`).
- `GOOGLE_APPLICATION_CREDENTIALS` — only for the legacy Google recognizer.
- `SSH_HOST`, `SSH_USER`, `SSH_PASSWORD`, `SSH_DEST_AUDIO_DB` — upload.

## Rules for agents

**Things that are expensive, interactive or destructive — don't run them on your own initiative:**

- Most `pg.py` commands open a **curses menu** and/or call `input()`; they hang or crash without a
  real TTY. Set `CODE=...` and pass the file argument where supported, or test the underlying
  `core` functions directly instead of going through the CLI.
- Anything that transcribes loads Whisper `large` (multi-GB model, slow). Anything that furiganates
  spends money on the LLM API.
- `process_incoming` removes source MP3s, `normalize_volumes` and `update` overwrite data in place,
  and `make upload` rsyncs with `--delete` to the live site. `audio_db/` is **not in git**, so there
  is no undo. Work on a copy (e.g. under the scratch/`temp` dir with `AUDIO_SOURCE_PATH` pointed at
  it) when you need to exercise the pipeline, and ask before touching the real DB or uploading.
- Never print, commit or copy the contents of `.env` or `cred/`.

**Verification.** No linter config or CI. After a change run `uv run pytest` (fast, no Whisper/LLM/network;
`tests/conftest.py` points `AUDIO_SOURCE_PATH` to a temp dir) and `uv run python -c "import pg"`
(catches import/syntax errors; prints a harmless pykakasi warning).
Pure logic — `SegmentManager`, `detect_pieces`, `process_numbered_list`, furigana regex
converters, `AudioIndexer` — can be checked with a short script against a temp directory.
New pure logic should come with tests in `tests/`.

**Trying the editor.** `.claude/launch.json` starts it against `temp/editor_db` — a small git-ignored copy of a few
files from the real DB (create it by copying a couple of `lb_*.mp3` + their `_segments.json` into
`temp/editor_db/<CODE>/`); its backups go to `temp/editor_backups`.
That launch config also sets `EDITOR_FAKE_AI=1`: transcribe/furigana jobs use placeholders instead of Whisper and the LLM,
so the whole job flow can be exercised for free. Never set it for real work.
It sets `EDITOR_UPLOAD_CMD=tests/bin/fake_upload.sh` as well: the upload wizard then runs that harmless script
instead of `scripts/upload.sh` (which always uploads the real DB from `.env`, whatever the editor looks at). Never point a dev server you are experimenting with at the real `audio_db/`.

**Code style.** Follow what is there: plain functions and small classes, `print()` for progress
(no logging framework), `tqdm` for loops, f-strings, `os.path` for paths, JSON written with
`ensure_ascii=False, indent=4`. Code, comments and commit messages are in English (a couple of
interactive prompts are in Russian — leave them). Commit messages are short imperative one-liners
("Indexer: digest", "Fix process-incoming"). Add dependencies with `uv add`, not by editing
`requirements.txt`.

**Adding a CLI command:** write the function in `pg.py`, register it in `command_map`, and add a
Makefile target with a `# description` comment (that comment is what `make help` prints).

## Known quirks (verify before relying on them; fix only if asked)

- `SegmentManager.convert_ruby_to_parenthesis()` iterates `for k, v in self.segments` — a leftover
  from the v2 dict format; it breaks on v3 lists, so the `convert_ruby` command is effectively dead.
- `make furiganate` handles a single file (`furigana_1`); the batch `furiganate_all` is only reachable
  through `process_incoming`.
- `FuriganaNeural.generate_furigana` only prints a warning when the LLM returns a different number of
  lines; `SegmentManager.update_texts` then raises `ValueError`, so nothing is saved for that file.
- `fill_text_for` iterates `segments_without_text`, so `skip_existing=False` alone does not force
  re-transcription — `update` works because it re-splits (which clears the texts) first.
- `ask_to_choose_the_code()` defaults the menu to `JPLTX` and raises if that directory doesn't exist.
- `AudioIndexer.save()` writes an absolute local `path` into `index.json`.
- `core/furigana.py` imports `MeCab` at module level and is imported by `segment_man`, so MeCab must be
  installed even though the classic furigana path is unused. `pykakasi` is optional and not installed.
- `readme.md` is lowercase while `pyproject.toml` says `readme = "README.md"` (harmless on macOS).
