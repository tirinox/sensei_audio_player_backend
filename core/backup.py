import filecmp
import os
import shutil
from datetime import datetime

from core.config import AUDIO_SOURCE_PATH, BACKUP_PATH
from core.segment_man import SegmentManager

KEEP_BACKUPS = 50
TIME_FORMAT = '%Y%m%d-%H%M%S-%f'


def backup_dir_for(filename, backup_root=None, source_root=None):
    """backups/<CODE>/<file>.mp3_segments.json/ for an MP3 (or its segments file) inside the audio DB"""
    segments_file = os.path.abspath(SegmentManager.segments_filename(filename))
    rel_path = os.path.relpath(segments_file, source_root or AUDIO_SOURCE_PATH)
    if rel_path.startswith('..'):
        raise ValueError(f"{filename} is outside of the audio DB")
    return os.path.join(backup_root or BACKUP_PATH, rel_path)


def list_backups(filename, backup_root=None, source_root=None):
    """Backup names, newest first"""
    backup_dir = backup_dir_for(filename, backup_root, source_root)
    if not os.path.isdir(backup_dir):
        return []
    return sorted((f for f in os.listdir(backup_dir) if f.endswith('.json')), reverse=True)


def parse_backup_name(name):
    """<time>_<label>.json -> (datetime, label); the label says what was about to happen to the file"""
    stem = name[:-len('.json')]
    time_part, _, label = stem.partition('_')
    return datetime.strptime(time_part, TIME_FORMAT), label


def make_backup(filename, backup_root=None, source_root=None, keep=KEEP_BACKUPS, label='', min_interval=0):
    """
    Copy the current segments file to the backup dir. Returns the backup name or None if nothing was copied.
    min_interval (seconds): skip if the latest backup has the same label and is newer than that,
    so a series of small edits (like typing texts) makes one backup.
    """
    backup_dir = backup_dir_for(filename, backup_root, source_root)

    segments_file = SegmentManager.segments_filename(filename)
    if not os.path.exists(segments_file):
        return None

    names = list_backups(filename, backup_root, source_root)
    if names and filecmp.cmp(os.path.join(backup_dir, names[0]), segments_file, shallow=False):
        return None
    if names and min_interval:
        last_time, last_label = parse_backup_name(names[0])
        if last_label == label and (datetime.now() - last_time).total_seconds() < min_interval:
            return None

    os.makedirs(backup_dir, exist_ok=True)
    name = datetime.now().strftime(TIME_FORMAT) + (f'_{label}' if label else '') + '.json'
    shutil.copyfile(segments_file, os.path.join(backup_dir, name))

    for old_name in names[max(keep - 1, 0):]:
        os.remove(os.path.join(backup_dir, old_name))

    return name


def restore_backup(filename, name, backup_root=None, source_root=None):
    """Put a backup back in place; the current version is backed up first, so restoring can be undone too"""
    if name not in list_backups(filename, backup_root, source_root):
        raise FileNotFoundError(f"No backup {name} for {filename}")

    make_backup(filename, backup_root, source_root, label='restore')

    backup_dir = backup_dir_for(filename, backup_root, source_root)
    shutil.copyfile(os.path.join(backup_dir, name), SegmentManager.segments_filename(filename))
