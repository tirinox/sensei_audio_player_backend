import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.config import AUDIO_SOURCE_PATH
from core.splitter import split_params
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


# must be the last one: it catches everything that is not matched above
app.mount("/", StaticFiles(directory=STATIC_PATH, html=True), name="static")
