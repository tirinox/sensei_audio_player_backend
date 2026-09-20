import json
import os
import threading
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import backup
from core.audio_utils import load_audio_file
from core.config import AUDIO_SOURCE_PATH
from core.segment_man import SegmentManager
from core.splitter import pick_cut, split_params
from editor import library

STATIC_PATH = os.path.join(os.path.dirname(__file__), 'static')

app = FastAPI(title="Sensei Audio Editor")


def check_code(code):
    if code not in library.list_codes(AUDIO_SOURCE_PATH):
        raise HTTPException(404, f"No such code: {code}")


@app.get("/api/codes")
def get_codes():
    codes = []
    for code in library.list_codes(AUDIO_SOURCE_PATH):
        codes.append({"code": code, "n_files": len(library.list_mp3_names(AUDIO_SOURCE_PATH, code))})
    return {"source_path": AUDIO_SOURCE_PATH, "codes": codes, "split_defaults": split_params()}


@app.get("/api/codes/{code}/files")
def get_files(code: str):
    check_code(code)
    return {"code": code, "files": library.list_files(AUDIO_SOURCE_PATH, code)}


@app.get("/api/codes/{code}/files/{name}")
def get_file(code: str, name: str):
    try:
        return library.file_details(AUDIO_SOURCE_PATH, code, name)
    except FileNotFoundError:
        raise HTTPException(404, f"No such file: {code}/{name}")


@app.get("/audio/{code}/{name}")
def get_audio(code: str, name: str):
    try:
        mp3_path = library.resolve_mp3(AUDIO_SOURCE_PATH, code, name)
    except FileNotFoundError:
        raise HTTPException(404, f"No such file: {code}/{name}")
    return FileResponse(mp3_path, media_type="audio/mpeg")


# ---- editing ----
# Every change is written to the segments file at once; the previous version goes to backups first.

TEXT_BACKUP_INTERVAL = 300  # seconds; a series of text edits makes one backup

edit_lock = threading.Lock()


class SegmentRef(BaseModel):
    # start/end of the segment as the browser sees it: the index alone is not enough
    # if the file was changed meanwhile (CLI, another tab)
    start: int
    end: int


class TextEdit(SegmentRef):
    text: Optional[str] = None
    original_text: Optional[str] = None


class SplitRequest(SegmentRef):
    at_ms: Optional[int] = None  # None: at the longest pause inside the segment


@lru_cache(maxsize=2)
def cached_audio(mp3_path, mtime):
    return load_audio_file(mp3_path)


def edit_segments(code, name, i, ref: SegmentRef, label, change, min_interval=0):
    try:
        mp3_path = library.resolve_mp3(AUDIO_SOURCE_PATH, code, name)
    except FileNotFoundError:
        raise HTTPException(404, f"No such file: {code}/{name}")

    with edit_lock:
        seg = SegmentManager(mp3_path)
        if not seg.load():
            raise HTTPException(409, "The file has no segments")
        if not 0 <= i < len(seg.segments) or (seg.segments[i]['start'], seg.segments[i]['end']) != (ref.start, ref.end):
            raise HTTPException(409, "The segments were changed by someone else, reload the file")

        try:
            change(seg, mp3_path)
        except (ValueError, IndexError) as e:
            raise HTTPException(400, str(e))

        backup.make_backup(mp3_path, label=label, min_interval=min_interval)
        seg.save()

    return library.file_details(AUDIO_SOURCE_PATH, code, name)


@app.put("/api/codes/{code}/files/{name}/segments/{i}/text")
def put_text(code: str, name: str, i: int, edit: TextEdit):
    def change(seg, _):
        if edit.text is not None:
            seg.set_text(i, edit.text.strip())
        if edit.original_text is not None:
            seg.set_original_text(i, edit.original_text.strip())

    return edit_segments(code, name, i, edit, 'text', change, min_interval=TEXT_BACKUP_INTERVAL)


@app.post("/api/codes/{code}/files/{name}/segments/{i}/join")
def join_with_next(code: str, name: str, i: int, ref: SegmentRef):
    return edit_segments(code, name, i, ref, 'join', lambda seg, _: seg.join_segments(i, i + 1))


@app.post("/api/codes/{code}/files/{name}/segments/{i}/delete")
def delete_segment(code: str, name: str, i: int, ref: SegmentRef):
    return edit_segments(code, name, i, ref, 'delete', lambda seg, _: seg.delete_segment(i))


@app.post("/api/codes/{code}/files/{name}/segments/{i}/drop_furigana")
def drop_furigana(code: str, name: str, i: int, ref: SegmentRef):
    return edit_segments(code, name, i, ref, 'text', lambda seg, _: seg.drop_furigana(i))


@app.post("/api/codes/{code}/files/{name}/segments/{i}/split")
def split_segment(code: str, name: str, i: int, request: SplitRequest):
    def change(seg, mp3_path):
        params = split_params()
        audio = cached_audio(mp3_path, os.path.getmtime(mp3_path))
        cut = pick_cut(audio, request.start, request.end, at_ms=request.at_ms,
                       padding=params['padding'], silence_thresh=params['silence_thresh'])
        if cut is None:
            raise ValueError("No pause found inside the segment; put the cursor where to cut")
        seg.split_segment(i, *cut)

    return edit_segments(code, name, i, request, 'split', change)


@app.get("/api/codes/{code}/files/{name}/backups")
def get_backups(code: str, name: str):
    try:
        mp3_path = library.resolve_mp3(AUDIO_SOURCE_PATH, code, name)
    except FileNotFoundError:
        raise HTTPException(404, f"No such file: {code}/{name}")

    backup_dir = backup.backup_dir_for(mp3_path)
    backups = []
    for backup_name in backup.list_backups(mp3_path):
        time, label = backup.parse_backup_name(backup_name)
        try:
            with open(os.path.join(backup_dir, backup_name), 'r') as f:
                n_segments = len(json.load(f)['segments'])
        except (json.JSONDecodeError, KeyError):
            n_segments = None
        backups.append({"name": backup_name, "time": time.isoformat(), "label": label, "n_segments": n_segments})
    return {"backups": backups}


@app.post("/api/codes/{code}/files/{name}/backups/{backup_name}/restore")
def restore_backup(code: str, name: str, backup_name: str):
    try:
        mp3_path = library.resolve_mp3(AUDIO_SOURCE_PATH, code, name)
        with edit_lock:
            backup.restore_backup(mp3_path, backup_name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return library.file_details(AUDIO_SOURCE_PATH, code, name)


# must be the last one: it catches everything that is not matched above
app.mount("/", StaticFiles(directory=STATIC_PATH, html=True), name="static")
