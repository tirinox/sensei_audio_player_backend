import json
import os

import pytest

from editor import library


def write_segments(mp3_path, segments):
    with open(mp3_path + '_segments.json', 'w') as f:
        json.dump({"version": 3, "length": 12.5, "title": "x", "segments": segments}, f, ensure_ascii=False)


@pytest.fixture
def db(tmp_path):
    code_path = tmp_path / 'JPTEST'
    code_path.mkdir()
    (tmp_path / 'other').mkdir()
    for name in ['new recording.mp3', 'lb_a.mp3', 'lb_b.mp3', 'lb_c.MP3', 'lb_d.mp3']:
        (code_path / name).write_bytes(b'')

    write_segments(str(code_path / 'lb_b.mp3'), [
        {"start": 0, "end": 1000, "text": "日"},
        {"start": 1500, "end": 2000, "text": ""},
    ])
    write_segments(str(code_path / 'lb_c.MP3'), [
        {"start": 0, "end": 1000, "text": "[日](ひ)", "original_text": "日"},
        {"start": 1500, "end": 2000, "text": "火"},
    ])
    write_segments(str(code_path / 'lb_d.mp3'), [
        {"start": 0, "end": 1000, "text": "[日](ひ)", "original_text": "日"},
    ])
    with open(code_path / 'index.json', 'w') as f:
        json.dump({"files": [
            {"audio_file": "lb_d.mp3", "n_segments": 1, "digest": "日", "title": "Custom", "length": 3.0},
            {"audio_file": "lb_c.MP3", "n_segments": 2, "digest": "old text", "title": "lb_c.MP3"},
        ]}, f, ensure_ascii=False)
    return str(tmp_path)


def test_codes(db):
    assert library.list_codes(db) == ['JPTEST']


def test_stages(db):
    files = {f['name']: f for f in library.list_files(db, 'JPTEST')}
    assert {name: f['stage'] for name, f in files.items()} == {
        'new recording.mp3': 'incoming',
        'lb_a.mp3': 'unsplit',
        'lb_b.mp3': 'no_text',
        'lb_c.MP3': 'no_furigana',
        'lb_d.mp3': 'done',
    }
    assert (files['lb_b.mp3']['n_segments'], files['lb_b.mp3']['n_text'], files['lb_b.mp3']['n_furigana']) == (2, 1, 0)
    assert files['lb_c.MP3']['n_furigana'] == 1


def test_index_state(db):
    files = {f['name']: f for f in library.list_files(db, 'JPTEST')}
    assert files['lb_d.mp3']['title'] == 'Custom'
    assert not files['lb_d.mp3']['index_stale']
    assert files['lb_c.MP3']['index_stale']  # digest differs
    assert files['lb_b.mp3']['index_stale'] and not files['lb_b.mp3']['in_index']
    assert not files['lb_a.mp3']['index_stale']  # nothing to index yet
    assert files['lb_a.mp3']['title'] == 'a'
    assert files['lb_c.MP3']['title'] == 'c.MP3'  # index title is just the file name


def test_details_and_path_safety(db):
    details = library.file_details(db, 'JPTEST', 'lb_b.mp3')
    assert details['code'] == 'JPTEST'
    assert len(details['segments']) == 2
    assert details['length'] == 12.5

    for code, name in [('JPTEST', '../other/x.mp3'), ('JPTEST', 'index.json'), ('JPTEST', 'nope.mp3'),
                       ('other', 'x.mp3'), ('..', 'lb_a.mp3')]:
        with pytest.raises(FileNotFoundError):
            library.resolve_mp3(db, code, name)
    assert library.resolve_mp3(db, 'JPTEST', 'lb_a.mp3') == os.path.join(db, 'JPTEST', 'lb_a.mp3')
