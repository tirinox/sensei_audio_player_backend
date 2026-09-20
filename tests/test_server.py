import json
import os
import shutil
import threading
import time
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from pydub import AudioSegment
from pydub.generators import Sine

from core.config import AUDIO_SOURCE_PATH, BACKUP_PATH
from editor import pipeline
from editor.server import app, jobs

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


# ---- re-splitting ----

def test_split_preview_and_apply(mp3_path, segments):
    preview = client.post(f'{URL}/split', json={"min_silence_len": 800, "padding": 200, "silence_thresh": -40}).json()
    assert len(preview['pieces']) == 2  # the 500 ms pause does not split
    assert saved_segments(mp3_path) == segments

    preview = client.post(f'{URL}/split', json={"min_silence_len": 300, "padding": 100, "silence_thresh": -40}).json()
    assert len(preview['pieces']) == 3
    assert preview['params'] == {"min_silence_len": 300, "padding": 100, "silence_thresh": -40}

    applied = client.post(f'{URL}/split', json={"min_silence_len": 300, "padding": 100, "preview": False}).json()
    assert [(s['start'], s['end']) for s in applied['segments']] == [(p['start'], p['end']) for p in preview['pieces']]
    assert all(s['text'] == '' for s in applied['segments']) and applied['stage'] == 'no_text'
    assert client.get(f'{URL}/backups').json()['backups'][0]['label'] == 'resplit'


def test_resplit_one_segment(mp3_path, segments):
    body = ref(segments[0], min_silence_len=300, padding=100, silence_thresh=-40)
    preview = client.post(f'{URL}/segments/0/resplit', json=body).json()['pieces']
    assert len(preview) == 2 and preview[0]['start'] == 300 and preview[1]['end'] == 3200
    assert saved_segments(mp3_path) == segments

    result = client.post(f'{URL}/segments/0/resplit', json={**body, "preview": False}).json()['segments']
    assert len(result) == 3
    assert result[2] == segments[1]  # the others are not touched
    assert [s['text'] for s in result[:2]] == ['', '']

    # parameters that do not split are not applied
    body = ref(result[2], min_silence_len=300, padding=100, preview=False)
    assert client.post(f'{URL}/segments/2/resplit', json=body).status_code == 400


def test_suggest_pause(mp3_path, segments):
    data = client.get(f'{URL}/suggest_pause').json()
    assert data['pauses'] == sorted(data['pauses']) and len(data['pauses']) == 2
    assert data['suggestion'] is None  # too few pauses to guess


# ---- jobs ----

def wait_jobs(timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        all_jobs = client.get('/api/jobs').json()['jobs']
        if not any(j['status'] in ('queued', 'running') for j in all_jobs):
            return all_jobs
        time.sleep(0.05)
    raise TimeoutError


@pytest.fixture
def fake_ai(monkeypatch):
    monkeypatch.setattr(pipeline, 'FAKE_AI', True)
    monkeypatch.setattr(pipeline.time, 'sleep', lambda seconds: None)
    jobs.start(capture_stdout=False)


def submit(kind, **extra):
    return client.post('/api/jobs', json={"kind": kind, "code": CODE, "name": NAME, **extra})


def test_transcribe_then_furigana(mp3_path, segments, fake_ai):
    client.post(f'{URL}/segments/0/split', json=ref(segments[0]))  # makes an empty segment
    assert submit('transcribe', then=['furigana']).status_code == 200
    all_jobs = wait_jobs()
    assert [(j['kind'], j['status']) for j in all_jobs[-2:]] == [('transcribe', 'done'), ('furigana', 'done')]
    assert all_jobs[-2]['progress'] == [1, 1]

    result = saved_segments(mp3_path)
    assert result[0]['text'] == segments[0]['text']  # furiganated before: not sent to the LLM again
    assert result[1]['original_text'].startswith('テスト') and result[1]['text'].endswith('＊')
    assert result[2] == {**segments[1], "text": "水＊", "original_text": "水"}
    assert client.get(URL).json()['stage'] == 'done'


def test_furigana_one_segment(mp3_path, segments, fake_ai):
    params = {"i": 0, **ref(segments[0])}
    assert submit('furigana_segment', params=params).status_code == 200
    wait_jobs()
    result = saved_segments(mp3_path)
    assert result[0] == {**segments[0], "text": "日と火＊"}  # made again from the plain text
    assert result[1] == segments[1]

    submit('furigana_segment', params={"i": 1, "start": 0, "end": 1})
    assert wait_jobs()[-1]['status'] == 'failed'


def test_job_validation_and_busy(mp3_path, segments, fake_ai, monkeypatch):
    assert submit('nope').status_code == 400
    assert submit('convert').status_code == 400  # it is lb_ already
    assert client.post('/api/jobs', json={"kind": "transcribe", "code": CODE, "name": "x.mp3"}).status_code == 404

    release = threading.Event()
    monkeypatch.setitem(jobs.handlers, 'split', lambda job, job_queue: release.wait(5))
    assert submit('split').status_code == 200
    try:
        assert client.get(URL).json()['busy']
        assert submit('transcribe').status_code == 423
        assert client.post(f'{URL}/segments/1/delete', json=ref(segments[1])).status_code == 423
        assert client.post(f'{URL}/split', json={"preview": False}).status_code == 423
        assert client.post(f'{URL}/split', json={}).status_code == 200  # a preview changes nothing
    finally:
        release.set()
    wait_jobs()
    assert not client.get(URL).json()['busy']
    assert saved_segments(mp3_path) == segments


def test_reindex_job(mp3_path, segments, fake_ai):
    assert client.get(URL).json()['index_stale']
    assert client.post('/api/jobs', json={"kind": "reindex", "code": CODE}).status_code == 200
    assert wait_jobs()[-1]['status'] == 'done'
    details = client.get(URL).json()
    assert details['in_index'] and not details['index_stale']


def test_convert_incoming(mp3_path, fake_ai):
    incoming = os.path.join(AUDIO_SOURCE_PATH, CODE, 'My Recording-7.mp3')
    shutil.copy(mp3_path, incoming)
    assert client.post(f'/api/codes/{CODE}/files/{quote("My Recording-7.mp3")}/split', json={}).status_code == 400

    response = client.post('/api/jobs', json={"kind": "convert", "code": CODE, "name": "My Recording-7.mp3",
                                              "then": ["split", "transcribe", "furigana"]})
    assert response.status_code == 200
    all_jobs = wait_jobs(30)
    assert all_jobs[-4]['result'] == 'lb_7.mp3'
    assert [(j['kind'], j['name'], j['status']) for j in all_jobs[-4:]] == [
        ('convert', 'My Recording-7.mp3', 'done'), ('split', 'lb_7.mp3', 'done'),
        ('transcribe', 'lb_7.mp3', 'done'), ('furigana', 'lb_7.mp3', 'done')]

    assert not os.path.exists(incoming)
    assert os.path.exists(os.path.join(BACKUP_PATH, 'originals', CODE, 'My Recording-7.mp3'))
    details = client.get(f'/api/codes/{CODE}/files/lb_7.mp3').json()
    assert details['stage'] == 'done' and details['n_segments'] == 2

    os.remove(os.path.join(AUDIO_SOURCE_PATH, CODE, 'lb_7.mp3'))
    os.remove(os.path.join(AUDIO_SOURCE_PATH, CODE, 'lb_7.mp3_segments.json'))


# ---- upload ----

@pytest.fixture
def fake_upload(monkeypatch, fake_ai):
    monkeypatch.setattr(pipeline, 'UPLOAD_CMD', os.path.join(os.path.dirname(__file__), 'bin', 'fake_upload.sh'))
    monkeypatch.setenv('AUDIO_SOURCE_PATH', AUDIO_SOURCE_PATH)


def upload_job(kind):
    return client.post('/api/jobs', json={"kind": kind})


def test_upload_needs_a_fresh_dry_run(mp3_path, segments, fake_upload):
    index_file = os.path.join(AUDIO_SOURCE_PATH, CODE, 'index.json')
    if os.path.exists(index_file):
        os.remove(index_file)  # left by the reindex test

    preflight = client.get('/api/upload/preflight').json()
    assert preflight['blocker'] is None and preflight['fake']
    report = next(c for c in preflight['codes'] if c['code'] == CODE)
    assert report['no_furigana'] == [NAME] and report['stale'] == 1

    jobs.jobs.clear()
    assert upload_job('upload').status_code == 409  # no dry run yet

    assert upload_job('upload_dry').status_code == 200
    dry = wait_jobs()[-1]
    assert dry['status'] == 'done'
    assert CODE in dry['data']['reindexed']
    assert f'{CODE}/index.json' in dry['data']['upload'] and f'{CODE}/{NAME}_segments.json' in dry['data']['upload']
    assert dry['data']['delete'] == ['JPTEST/lb_removed_on_disk.mp3_segments.json', 'JPTEST/lb_removed_on_disk.mp3']
    assert not client.get(URL).json()['index_stale']  # reindexed by the dry run

    # an edit after the dry run makes the index stale again: the check has to be repeated
    client.put(f'{URL}/segments/1/text', json=ref(segments[1], text='水曜日'))
    assert upload_job('upload').status_code == 409

    upload_job('upload_dry')
    wait_jobs()
    assert upload_job('upload').status_code == 200
    done = wait_jobs()[-1]
    assert (done['kind'], done['status']) == ('upload', 'done')
    assert upload_job('upload').status_code == 409  # one dry run allows one upload


def test_upload_failure_and_blocker(mp3_path, segments, fake_upload, monkeypatch):
    monkeypatch.setenv('FAKE_UPLOAD_FAIL', '1')
    upload_job('upload_dry')
    failed = wait_jobs()[-1]
    assert failed['status'] == 'failed' and 'code 12' in failed['error']
    assert upload_job('upload').status_code == 409

    # the real script reads .env itself: the editor must look at the same directory
    monkeypatch.setattr(pipeline, 'UPLOAD_CMD', None)
    blocker = client.get('/api/upload/preflight').json()['blocker']
    assert blocker and upload_job('upload_dry').status_code == 409


def test_parse_rsync(tmp_path):
    (tmp_path / 'JPX').mkdir()
    (tmp_path / 'JPX' / 'lb_あ.mp3').write_bytes(b'')
    lines = ['building file list ... done', 'JPX/', 'JPX/lb_\\#343\\#201\\#202.mp3', 'deleting JPX/old.mp3',
             'JPX/not on disk.mp3', '', 'sent 1 bytes']
    assert pipeline.parse_rsync(lines, str(tmp_path)) == {"upload": ['JPX/lb_あ.mp3'], "delete": ['JPX/old.mp3']}
