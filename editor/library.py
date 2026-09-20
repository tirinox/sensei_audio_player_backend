import json
import os

from core.file_man import get_all_codes, is_processed_mp3_lb
from core.indexer import AudioIndexer
from core.segment_man import SegmentManager


def list_codes(source_path):
    return sorted(get_all_codes(source_path))


def list_mp3_names(source_path, code):
    code_path = os.path.join(source_path, code)
    return sorted(f for f in os.listdir(code_path)
                  if f.lower().endswith('.mp3') and os.path.isfile(os.path.join(code_path, f)))


def resolve_mp3(source_path, code, name):
    """Full path of an MP3, only if it is really a file of that code (names come from the browser)"""
    if code not in get_all_codes(source_path) or name not in list_mp3_names(source_path, code):
        raise FileNotFoundError(f"{code}/{name}")
    return os.path.join(source_path, code, name)


def load_index_entries(source_path, code):
    index_file = os.path.join(source_path, code, 'index.json')
    try:
        with open(index_file, 'r') as f:
            return {entry['audio_file']: entry for entry in json.load(f)['files']}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return {}


def display_title(name, index_entry=None):
    # reindex puts the bare file name as the title, unless a custom one was set in index.json
    title = (index_entry or {}).get('title')
    if not title or title == name:
        title = AudioIndexer.beautify_title(name)
    return title


def file_status(mp3_path, index_entry=None):
    """
    What is done for the file: converted (lb_) -> split -> transcribed -> furiganated -> indexed.
    A segment counts as furiganated when it has original_text.
    """
    name = os.path.basename(mp3_path)
    seg = SegmentManager(mp3_path)
    has_segments = seg.load()
    segments = seg.segments

    status = {
        "name": name,
        "title": display_title(name, index_entry),
        "processed": is_processed_mp3_lb(mp3_path),
        "has_segments": has_segments,
        "n_segments": len(segments),
        "n_text": sum(1 for s in segments if s.get('text')),
        "n_corrected": sum(1 for s in segments if 'raw_text' in s),
        "n_furigana": sum(1 for s in segments if 'original_text' in s),
        "length": seg.length or (index_entry or {}).get('length') or 0,
        "in_index": index_entry is not None,
    }
    status["index_stale"] = has_segments and (
            index_entry is None
            or index_entry.get('n_segments') != len(segments)
            or index_entry.get('digest', '') != seg.get_digest()
    )
    status["stage"] = file_stage(status)
    return status, seg


def file_stage(status):
    if not status["processed"]:
        return "incoming"
    if not status["has_segments"] or not status["n_segments"]:
        return "unsplit"
    if status["n_text"] < status["n_segments"]:
        return "no_text"
    if status["n_furigana"] < status["n_segments"]:
        return "no_furigana"
    return "done"


def list_files(source_path, code):
    index_entries = load_index_entries(source_path, code)
    files = []
    for name in list_mp3_names(source_path, code):
        status, _ = file_status(os.path.join(source_path, code, name), index_entries.get(name))
        files.append(status)
    return files


def file_details(source_path, code, name):
    mp3_path = resolve_mp3(source_path, code, name)
    status, seg = file_status(mp3_path, load_index_entries(source_path, code).get(name))
    status["code"] = code
    status["segments"] = seg.segments
    return status


def upload_report(source_path):
    """Per code: what is not finished yet. Everything in the audio DB goes to the host, finished or not"""
    report = []
    for code in list_codes(source_path):
        files = list_files(source_path, code)
        entry = {"code": code, "n_files": len(files), "stale": sum(1 for f in files if f["index_stale"])}
        for stage in ("incoming", "unsplit", "no_text", "no_furigana"):
            entry[stage] = [f["name"] for f in files if f["stage"] == stage]
        report.append(entry)
    return report
