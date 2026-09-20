import json
import os
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from pydub import AudioSegment
from pydub.generators import Sine

from core.config import AUDIO_SOURCE_PATH
from editor.server import app

client = TestClient(app)

CODE = 'JPSRV'
NAME = 'lb_テスト.mp3'
URL = f'/api/codes/{CODE}/files/{quote(NAME)}'


def tone(ms):
    return Sine(440).to_audio_segment(duration=ms, volume=-10)


@pytest.fixture(scope='module')
def mp3_path():
    os.makedirs(os.path.join(AUDIO_SOURCE_PATH, CODE), exist_ok=True)
    path = os.path.join(AUDIO_SOURCE_PATH, CODE, NAME)
    silence = AudioSegment.silent
    # phrases at 0.5-1.5 and 2.0-3.0 (one segment), 4.0-5.0
    audio = silence(500) + tone(1000) + silence(500) + tone(1000) + silence(1000) + tone(1000) + silence(500)
    audio.export(path, format='mp3')
    return path


@pytest.fixture
def segments(mp3_path):
    data = {"version": 3, "length": 5.5, "title": "Test", "segments": [
        {"start": 300, "end": 3200, "text": "[日](ひ)と[火](ひ)", "original_text": "日と火"},
        {"start": 3800, "end": 5200, "text": "水"},
    ]}
    with open(mp3_path + '_segments.json', 'w') as f:
        json.dump(data, f, ensure_ascii=False)
    return data['segments']


def saved_segments(mp3_path):
    with open(mp3_path + '_segments.json') as f:
        return json.load(f)['segments']


def ref(segment, **extra):
    return {"start": segment['start'], "end": segment['end'], **extra}


def test_read(mp3_path, segments):
    assert CODE in [c['code'] for c in client.get('/api/codes').json()['codes']]
    files = client.get(f'/api/codes/{CODE}/files').json()['files']
    assert [f['stage'] for f in files] == ['no_furigana']
    assert client.get(URL).json()['segments'] == segments
    assert client.get(f'/audio/{CODE}/{quote(NAME)}').status_code == 200
    assert client.get(f'/api/codes/{CODE}/files/nope.mp3').status_code == 404
    assert client.get('/api/codes/NOPE/files').status_code == 404


def test_edit_text(mp3_path, segments):
    response = client.put(f'{URL}/segments/1/text', json=ref(segments[1], text=' 水曜日 '))
    assert response.status_code == 200
    assert response.json()['segments'][1] == {"start": 3800, "end": 5200, "text": "水曜日"}
    assert saved_segments(mp3_path)[1]['text'] == '水曜日'

    response = client.put(f'{URL}/segments/0/text', json=ref(segments[0], original_text='日と火。'))
    assert response.json()['segments'][0]['original_text'] == '日と火。'

    # plain segments do not get original_text
    assert client.put(f'{URL}/segments/1/text', json=ref(segments[1], original_text='x')).status_code == 400


def test_stale_reference_is_rejected(mp3_path, segments):
    assert client.put(f'{URL}/segments/1/text', json={"start": 1, "end": 2, "text": "x"}).status_code == 409
    assert client.post(f'{URL}/segments/5/delete', json=ref(segments[1])).status_code == 409
    assert saved_segments(mp3_path) == segments


def test_join_delete(mp3_path, segments):
    joined = client.post(f'{URL}/segments/0/join', json=ref(segments[0])).json()['segments']
    assert joined == [{"start": 300, "end": 5200, "text": "[日](ひ)と[火](ひ) 水", "original_text": "日と火 水"}]
    assert client.post(f'{URL}/segments/0/join', json=ref(joined[0])).status_code == 400  # no next one

    details = client.post(f'{URL}/segments/0/delete', json=ref(joined[0])).json()
    assert details['segments'] == [] and details['stage'] == 'unsplit'


def test_split_auto_and_at_cursor(mp3_path, segments):
    result = client.post(f'{URL}/segments/0/split', json=ref(segments[0])).json()['segments']
    assert len(result) == 3
    first, second = result[0], result[1]
    assert first['text'] == segments[0]['text'] and first['original_text'] == '日と火'
    assert second['text'] == '' and 'original_text' not in second
    # the pause is 1500..2000: the parts keep 200 ms of padding each
    assert abs(first['end'] - 1700) <= 60 and abs(second['start'] - 1800) <= 60
    assert (first['start'], second['end']) == (300, 3200)

    # no pause inside the second part: auto fails, the cursor works
    assert client.post(f'{URL}/segments/1/split', json=ref(second)).status_code == 400
    result = client.post(f'{URL}/segments/1/split', json=ref(second, at_ms=2500)).json()['segments']
    assert [(s['start'], s['end']) for s in result[1:3]] == [(second['start'], 2500), (2500, 3200)]
    assert client.post(f'{URL}/segments/1/split', json=ref(result[1], at_ms=9999)).status_code == 400


def test_backups_and_restore(mp3_path, segments):
    before = len(client.get(f'{URL}/backups').json()['backups'])
    client.post(f'{URL}/segments/1/delete', json=ref(segments[1]))
    backups = client.get(f'{URL}/backups').json()['backups']
    assert len(backups) == before + 1
    assert backups[0]['label'] == 'delete' and backups[0]['n_segments'] == 2

    restored = client.post(f'{URL}/backups/{backups[0]["name"]}/restore').json()
    assert restored['segments'] == segments
    assert client.get(f'{URL}/backups').json()['backups'][0]['label'] == 'restore'
    assert client.post(f'{URL}/backups/nope.json/restore').status_code == 404
