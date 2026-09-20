"""Job handlers: the steps of pg.py process_incoming, one file at a time, without menus and input()"""
import os
import re
import shutil
import subprocess
import time

from core import backup
from core.audio_utils import convert_mp3_to_low_bitrate, load_audio_file
from core.config import AUDIO_SOURCE_PATH, BACKUP_PATH
from core.file_man import is_processed_mp3_lb
from core.indexer import AudioIndexer
from core.segment_man import SegmentManager
from core.splitter import split_file
from editor import library

# EDITOR_FAKE_AI=1: no Whisper and no LLM, just placeholders; to try the UI without loading the model and paying
FAKE_AI = bool(os.environ.get('EDITOR_FAKE_AI'))


class FakeRecognizer:
    def recognize(self, audio_segment):
        time.sleep(0.7)
        return f"テスト{len(audio_segment)}ミリ秒"


class FakeFuriganator:
    def generate_furigana(self, sentences):
        time.sleep(1.5)
        return [sentence.replace('秒', '[秒](びょう)') + '＊' for sentence in sentences]

    def generate_furigana_one(self, sentence):
        return self.generate_furigana([sentence])[0]


def get_recognizer():
    return FakeRecognizer() if FAKE_AI else None  # None: fill_text_for loads Whisper once and keeps it


def get_furiganator():
    if FAKE_AI:
        return FakeFuriganator()
    from core.furigana_neural import FuriganaNeural
    return FuriganaNeural.from_env()


def mp3_of(job):
    return library.resolve_mp3(AUDIO_SOURCE_PATH, job.code, job.name)


def load_segments(job):
    mp3_path = mp3_of(job)
    seg = SegmentManager(mp3_path)
    if not seg.load():
        raise ValueError("The file is not split into segments yet")
    return mp3_path, seg


def convert(job, jobs):
    """Incoming MP3 -> normalized low bitrate lb_*.mp3. The original is moved out of the audio DB, not deleted"""
    mp3_path = mp3_of(job)
    if is_processed_mp3_lb(mp3_path):
        raise ValueError("The file is converted already")

    new_path = convert_mp3_to_low_bitrate(mp3_path, normalize_volume=True)
    if not os.path.exists(new_path) or not os.path.getsize(new_path):
        raise ValueError("ffmpeg did not produce the converted file")

    originals_dir = os.path.join(BACKUP_PATH, 'originals', job.code)
    os.makedirs(originals_dir, exist_ok=True)
    shutil.move(mp3_path, os.path.join(originals_dir, os.path.basename(mp3_path)))
    print(f"The original is moved to {originals_dir}")
    return os.path.basename(new_path)


def split(job, jobs):
    mp3_path = mp3_of(job)
    seg = SegmentManager(mp3_path)
    seg.load()
    backup.make_backup(mp3_path, label='resplit')
    split_file(load_audio_file(mp3_path), seg, **job.params)
    seg.save()
    print(f"{len(seg.segments)} segments")


def transcribe(job, jobs):
    from core.process_segments import fill_text_for  # imports whisper/torch: slow, so only when needed

    mp3_path, seg = load_segments(job)
    if not seg.segments_without_text:
        print("All segments have text already")
        return
    backup.make_backup(mp3_path, label='transcribe')
    fill_text_for(seg, sr=get_recognizer(), on_progress=lambda done, total: jobs.set_progress(job, done, total))


def furigana(job, jobs):
    """Only the segments that are not furiganated yet (all=True: every segment, from its plain text)"""
    mp3_path, seg = load_segments(job)
    redo_all = job.params.get('all', False)
    targets = [i for i, s in enumerate(seg.segments) if s.get('text') and (redo_all or 'original_text' not in s)]
    if not targets:
        print("Nothing to furiganate")
        return

    sentences = [seg.segments[i].get('original_text', seg.segments[i]['text']) for i in targets]
    lines = get_furiganator().generate_furigana(sentences)
    lines = [line for line in lines if line.strip()]
    if len(lines) != len(sentences):
        raise ValueError(f"The LLM returned {len(lines)} lines for {len(sentences)} sentences, nothing is saved")

    backup.make_backup(mp3_path, label='furigana')
    for i, line in zip(targets, lines):
        seg.set_furigana(i, line.strip())
    seg.save()


def furigana_segment(job, jobs):
    mp3_path, seg = load_segments(job)
    i, start, end = job.params['i'], job.params['start'], job.params['end']
    if not 0 <= i < len(seg.segments) or (seg.segments[i]['start'], seg.segments[i]['end']) != (start, end):
        raise ValueError("The segments were changed meanwhile")

    segment = seg.segments[i]
    sentence = segment.get('original_text', segment['text'])
    if not sentence:
        raise ValueError("The segment has no text")

    line = get_furiganator().generate_furigana_one(sentence)
    backup.make_backup(mp3_path, label='furigana')
    seg.set_furigana(i, line.strip())
    seg.save()


def reindex_code(code):
    indexer = AudioIndexer.from_code(code)
    indexer.rebuild_index_and_save()
    indexer.sort_files()
    indexer.save()
    print(f"{code}: {len(indexer.files)} files in the index")


def reindex(job, jobs):
    reindex_code(job.code)


# ---- upload: scripts/upload.sh (rsync --delete to the production host) ----

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# EDITOR_UPLOAD_CMD: another command instead of scripts/upload.sh (tests, trying the UI); it gets --dry-run too
UPLOAD_CMD = os.environ.get('EDITOR_UPLOAD_CMD')


def upload_blocker():
    """
    upload.sh takes AUDIO_SOURCE_PATH from .env on its own. If the editor was started with another path,
    what it shows is not what would be uploaded (and --delete would mirror that other directory): refuse.
    """
    if UPLOAD_CMD:
        return None

    from dotenv import dotenv_values
    env_file = os.path.join(PROJECT_ROOT, '.env')
    if not os.path.exists(env_file):
        return ".env is not found, scripts/upload.sh can not work"
    upload_path = dotenv_values(env_file).get('AUDIO_SOURCE_PATH') or ''
    upload_path = os.path.realpath(os.path.join(PROJECT_ROOT, upload_path))
    if upload_path != os.path.realpath(AUDIO_SOURCE_PATH):
        return f"The editor works with {AUDIO_SOURCE_PATH}, but scripts/upload.sh would upload {upload_path}"
    return None


def run_upload(dry_run):
    command = [UPLOAD_CMD or os.path.join(PROJECT_ROOT, 'scripts', 'upload.sh')]
    if dry_run:
        command.append('--dry-run')

    process = subprocess.Popen(command, cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace')
    lines = []
    for line in process.stdout:
        line = line.rstrip('\n')
        lines.append(line)
        print(line)
    if process.wait() != 0:
        raise ValueError(f"The upload script failed with code {process.returncode}, see the log")
    return lines


def unescape_rsync(line):
    """rsync prints non-ASCII bytes as \\#343\\#201\\#202 when the locale is not UTF-8"""
    if '\\#' not in line:
        return line
    raw = re.sub(rb'\\#(\d{3})', lambda m: bytes([int(m.group(1), 8)]), line.encode('utf-8'))
    return raw.decode('utf-8', errors='replace')


def parse_rsync(lines, source_path):
    """What rsync -v is going to do: files to send (they exist under source_path) and paths to delete on the host"""
    to_upload, to_delete = [], []
    for line in lines:
        line = unescape_rsync(line.strip())
        if line.startswith('deleting '):
            to_delete.append(line[len('deleting '):])
        elif line and not line.endswith('/') and os.path.isfile(os.path.join(source_path, line)):
            to_upload.append(line)
    return {"upload": to_upload, "delete": to_delete}


def upload_dry(job, jobs):
    """Bring index.json up to date, then ask rsync what it would do"""
    reindexed = [entry["code"] for entry in library.upload_report(AUDIO_SOURCE_PATH) if entry["stale"]]
    for code in reindexed:
        reindex_code(code)
    job.data = {**parse_rsync(run_upload(dry_run=True), AUDIO_SOURCE_PATH), "reindexed": reindexed}
    print(f"{len(job.data['upload'])} files to upload, {len(job.data['delete'])} to delete on the host")


def upload(job, jobs):
    job.data = parse_rsync(run_upload(dry_run=False), AUDIO_SOURCE_PATH)


HANDLERS = {
    "convert": convert,
    "split": split,
    "transcribe": transcribe,
    "furigana": furigana,
    "furigana_segment": furigana_segment,
    "reindex": reindex,
    "upload_dry": upload_dry,
    "upload": upload,
}
