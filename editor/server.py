import json
import os
import queue
import threading
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import backup
from core.audio_utils import load_audio_file
from core.config import AUDIO_SOURCE_PATH
from core.segment_man import SegmentManager
from core.file_man import is_processed_mp3_lb
from core.splitter import detect_pieces, detect_pieces_in_range, pick_cut, split_params, suggest_min_silence_len
from editor import library, pipeline
from editor.jobs import JobQueue

STATIC_PATH = os.path.join(os.path.dirname(__file__), 'static')

jobs = JobQueue(pipeline.HANDLERS)


@asynccontextmanager
async def lifespan(_):
    jobs.start()
    yield


app = FastAPI(title="Sensei Audio Editor", lifespan=lifespan)


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
    files = library.list_files(AUDIO_SOURCE_PATH, code)
    for f in files:
        f["busy"] = jobs.is_busy(code, f["name"])
    return {"code": code, "files": files}


@app.get("/api/codes/{code}/files/{name}")
def get_file(code: str, name: str):
    return file_details(code, name)


def file_details(code, name):
    try:
        details = library.file_details(AUDIO_SOURCE_PATH, code, name)
    except FileNotFoundError:
        raise HTTPException(404, f"No such file: {code}/{name}")
    details["busy"] = jobs.is_busy(code, name)
    return details


def resolve_or_404(code, name):
    try:
        return library.resolve_mp3(AUDIO_SOURCE_PATH, code, name)
    except FileNotFoundError:
        raise HTTPException(404, f"No such file: {code}/{name}")


def check_not_busy(code, name):
    if jobs.is_busy(code, name):
        raise HTTPException(423, "A job is queued or running for this file, wait until it finishes")


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
    mp3_path = resolve_or_404(code, name)
    check_not_busy(code, name)

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

    return file_details(code, name)


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


@app.post("/api/codes/{code}/files/{name}/segments/{i}/revert_correction")
def revert_correction(code: str, name: str, i: int, ref: SegmentRef):
    return edit_segments(code, name, i, ref, 'text', lambda seg, _: seg.revert_correction(i))


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
    mp3_path = resolve_or_404(code, name)
    check_not_busy(code, name)
    try:
        with edit_lock:
            backup.restore_backup(mp3_path, backup_name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return file_details(code, name)


# ---- re-splitting: fast enough to be done right in the request, with a preview ----

class SplitParams(BaseModel):
    min_silence_len: Optional[int] = None
    padding: Optional[int] = None
    silence_thresh: Optional[int] = None
    preview: bool = True  # only return the pieces, do not save

    def resolved(self):
        params = split_params(self.min_silence_len, self.padding, self.silence_thresh)
        if params['min_silence_len'] < 50 or params['padding'] < 0:
            raise HTTPException(400, "Bad split parameters")
        return params


class ResplitSegment(SplitParams, SegmentRef):
    pass


def audio_of(mp3_path):
    return cached_audio(mp3_path, os.path.getmtime(mp3_path))


def pieces_response(pieces, params):
    return {"pieces": [{"start": start, "end": end} for start, end in pieces], "params": params}


@app.get("/api/codes/{code}/files/{name}/suggest_pause")
def suggest_pause(code: str, name: str):
    mp3_path = resolve_or_404(code, name)
    params = split_params()
    suggestion, lengths = suggest_min_silence_len(audio_of(mp3_path), silence_thresh=params['silence_thresh'])
    return {"suggestion": suggestion, "pauses": lengths, "params": params}


@app.post("/api/codes/{code}/files/{name}/split")
def split_whole_file(code: str, name: str, request: SplitParams):
    mp3_path = resolve_or_404(code, name)
    if not is_processed_mp3_lb(mp3_path):
        raise HTTPException(400, "Convert the file first")
    params = request.resolved()
    pieces = detect_pieces(audio_of(mp3_path), **params)
    if request.preview:
        return pieces_response(pieces, params)

    check_not_busy(code, name)
    with edit_lock:
        seg = SegmentManager(mp3_path)
        seg.load()
        backup.make_backup(mp3_path, label='resplit')
        seg.set_segments(pieces)
        seg.save()
    return file_details(code, name)


@app.post("/api/codes/{code}/files/{name}/segments/{i}/resplit")
def resplit_segment(code: str, name: str, i: int, request: ResplitSegment):
    mp3_path = resolve_or_404(code, name)
    params = request.resolved()
    pieces = detect_pieces_in_range(audio_of(mp3_path), request.start, request.end, **params)
    if request.preview:
        return pieces_response(pieces, params)

    if len(pieces) < 2:
        raise HTTPException(400, "These parameters do not split the segment")
    return edit_segments(code, name, i, request, 'resplit', lambda seg, _: seg.replace_segment(i, pieces))


# ---- jobs: the slow steps (Whisper, LLM, ffmpeg) run one by one in the background ----

FILE_JOB_KINDS = ('convert', 'split', 'transcribe', 'correct', 'correct_segment', 'furigana', 'furigana_segment')


UPLOAD_JOB_KINDS = ('upload_dry', 'upload')
DRY_RUN_VALID_SECONDS = 15 * 60


class JobRequest(BaseModel):
    kind: str
    code: Optional[str] = None
    name: Optional[str] = None
    params: dict = {}
    then: List[str] = []


@app.get("/api/jobs")
def get_jobs():
    return {"jobs": jobs.snapshot(), "fake_ai": pipeline.FAKE_AI}


@app.post("/api/jobs")
def submit_job(request: JobRequest):
    for kind in [request.kind, *request.then]:
        if kind not in pipeline.HANDLERS:
            raise HTTPException(400, f"Unknown job kind: {kind}")

    if request.kind in UPLOAD_JOB_KINDS:
        check_upload_allowed(request.kind)
        return jobs.submit(request.kind).to_dict()

    check_code(request.code)

    if request.kind in FILE_JOB_KINDS:
        if not request.name:
            raise HTTPException(400, "File name is required")
        mp3_path = resolve_or_404(request.code, request.name)
        if (request.kind == 'convert') == is_processed_mp3_lb(mp3_path):
            raise HTTPException(400, "Incoming files can only be converted, and converted ones can not be converted again")
        check_not_busy(request.code, request.name)
        name = request.name
    else:
        name = None

    job = jobs.submit(request.kind, request.code, name, params=request.params, then=request.then)
    return job.to_dict()


def check_upload_allowed(kind):
    blocker = pipeline.upload_blocker()
    if blocker:
        raise HTTPException(409, blocker)
    if jobs.has_active():
        raise HTTPException(409, "Wait until the other jobs finish")
    if kind == 'upload':
        # only right after a successful dry run that still describes what is on the disk
        last = jobs.last_finished(UPLOAD_JOB_KINDS)
        fresh = last and last.kind == 'upload_dry' and last.status == 'done' \
            and time.time() - last.finished < DRY_RUN_VALID_SECONDS
        stale = any(entry["stale"] for entry in library.upload_report(AUDIO_SOURCE_PATH))
        if not fresh or stale:
            raise HTTPException(409, "Run the check (dry run) again: there is no recent one, or files changed since")


@app.get("/api/upload/preflight")
def upload_preflight():
    last = jobs.last_finished(UPLOAD_JOB_KINDS)
    return {
        "blocker": pipeline.upload_blocker(),
        "fake": bool(pipeline.UPLOAD_CMD),
        "source_path": AUDIO_SOURCE_PATH,
        "codes": library.upload_report(AUDIO_SOURCE_PATH),
        "last": last.to_dict() if last else None,
    }


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    if not jobs.cancel(job_id):
        raise HTTPException(409, "Only queued jobs can be cancelled")
    return {"ok": True}


@app.get("/api/events")
def events():
    def sse(event):
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    def stream():
        subscriber = jobs.subscribe()
        try:
            yield sse({"type": "jobs", "jobs": jobs.snapshot(), "fake_ai": pipeline.FAKE_AI})
            idle = 0
            while True:
                try:
                    yield sse(subscriber.get(timeout=1))
                    idle = 0
                except queue.Empty:
                    idle += 1
                    if idle % 15 == 0:
                        yield ": ping\n\n"
        finally:
            jobs.unsubscribe(subscriber)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# must be the last one: it catches everything that is not matched above
app.mount("/", StaticFiles(directory=STATIC_PATH, html=True), name="static")
