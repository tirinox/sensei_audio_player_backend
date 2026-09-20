import os

import pytest

from core.backup import backup_dir_for, list_backups, make_backup, parse_backup_name, restore_backup


@pytest.fixture
def roots(tmp_path):
    source_root = tmp_path / 'audio_db'
    (source_root / 'JPTEST').mkdir(parents=True)
    return {"backup_root": str(tmp_path / 'backups'), "source_root": str(source_root)}


def write(path, content):
    with open(path, 'w') as f:
        f.write(content)


def read(path):
    with open(path) as f:
        return f.read()


def test_backup_and_restore(roots):
    mp3 = os.path.join(roots['source_root'], 'JPTEST', 'lb_a.mp3')
    segments_file = mp3 + '_segments.json'

    assert make_backup(mp3, **roots) is None  # nothing to back up yet
    assert list_backups(mp3, **roots) == []

    write(segments_file, 'v1')
    first = make_backup(mp3, **roots)
    assert first
    assert make_backup(mp3, **roots) is None  # unchanged since the last backup
    assert backup_dir_for(mp3, **roots) == os.path.join(roots['backup_root'], 'JPTEST', 'lb_a.mp3_segments.json')

    write(segments_file, 'v2')
    second = make_backup(segments_file, **roots)  # segments file name works too
    assert list_backups(mp3, **roots) == [second, first]

    write(segments_file, 'v3')
    restore_backup(mp3, first, **roots)
    assert read(segments_file) == 'v1'

    # v3 was saved before restoring
    names = list_backups(mp3, **roots)
    assert len(names) == 3
    assert read(os.path.join(backup_dir_for(mp3, **roots), names[0])) == 'v3'


def test_prune(roots):
    mp3 = os.path.join(roots['source_root'], 'JPTEST', 'lb_a.mp3')
    for i in range(6):
        write(mp3 + '_segments.json', f'v{i}')
        make_backup(mp3, keep=3, **roots)
    names = list_backups(mp3, **roots)
    assert len(names) == 3
    assert read(os.path.join(backup_dir_for(mp3, **roots), names[0])) == 'v5'


def test_rejects_bad_names_and_paths(roots, tmp_path):
    mp3 = os.path.join(roots['source_root'], 'JPTEST', 'lb_a.mp3')
    write(mp3 + '_segments.json', 'v1')
    make_backup(mp3, **roots)
    with pytest.raises(FileNotFoundError):
        restore_backup(mp3, '../../../etc/passwd', **roots)
    with pytest.raises(ValueError):
        make_backup(str(tmp_path / 'outside.mp3'), **roots)


def test_labels_and_min_interval(roots):
    mp3 = os.path.join(roots['source_root'], 'JPTEST', 'lb_a.mp3')
    segments_file = mp3 + '_segments.json'

    write(segments_file, 'v1')
    first = make_backup(mp3, label='text', min_interval=300, **roots)
    assert first.endswith('_text.json')
    assert parse_backup_name(first)[1] == 'text'

    write(segments_file, 'v2')
    assert make_backup(mp3, label='text', min_interval=300, **roots) is None  # same series of text edits

    join = make_backup(mp3, label='join', min_interval=300, **roots)  # another kind of change is never skipped
    assert join

    write(segments_file, 'v3')
    assert make_backup(mp3, label='text', min_interval=300, **roots)  # the latest one is not a text backup
    assert len(list_backups(mp3, **roots)) == 3
