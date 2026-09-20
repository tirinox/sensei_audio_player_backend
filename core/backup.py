import filecmp
import os
import shutil
from datetime import datetime

from core.config import AUDIO_SOURCE_PATH, BACKUP_PATH
from core.segment_man import SegmentManager

KEEP_BACKUPS = 50


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


def make_backup(filename, backup_root=None, source_root=None, keep=KEEP_BACKUPS):
    """Copy the current segments file to the backup dir. Returns the backup name or None if nothing was copied"""
    backup_dir = backup_dir_for(filename, backup_root, source_root)

    segments_file = SegmentManager.segments_filename(filename)
    if not os.path.exists(segments_file):
        return None

    names = list_backups(filename, backup_root, source_root)
    if names and filecmp.cmp(os.path.join(backup_dir, names[0]), segments_file, shallow=False):
        return None

    os.makedirs(backup_dir, exist_ok=True)
    name = datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json'
    shutil.copyfile(segments_file, os.path.join(backup_dir, name))

    for old_name in names[max(keep - 1, 0):]:
        os.remove(os.path.join(backup_dir, old_name))

    return name


def restore_backup(filename, name, backup_root=None, source_root=None):
    """Put a backup back in place; the current version is backed up first, so restoring can be undone too"""
    if name not in list_backups(filename, backup_root, source_root):
        raise FileNotFoundError(f"No backup {name} for {filename}")

    make_backup(filename, backup_root, source_root)

    backup_dir = backup_dir_for(filename, backup_root, source_root)
    shutil.copyfile(os.path.join(backup_dir, name), SegmentManager.segments_filename(filename))
