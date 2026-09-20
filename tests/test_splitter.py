import pytest
from pydub import AudioSegment
from pydub.generators import Sine, WhiteNoise
from pydub.silence import detect_silence as pydub_detect_silence

from core.segment_man import SegmentManager
from core.splitter import detect_pieces, detect_pieces_in_range, detect_silence, find_pauses, pick_cut, split_file, \
    split_params, suggest_min_silence_len


def tone(ms):
    return Sine(440).to_audio_segment(duration=ms, volume=-10)


def silence(ms):
    return AudioSegment.silent(duration=ms)


PARAMS = dict(padding=200, min_silence_len=800, silence_thresh=-40)


def approx(pieces, expected, tolerance=30):
    assert len(pieces) == len(expected), pieces
    for (start, end), (exp_start, exp_end) in zip(pieces, expected):
        assert abs(start - exp_start) <= tolerance and abs(end - exp_end) <= tolerance, pieces


def test_leading_and_trailing_silence():
    audio = silence(1000) + tone(2000) + silence(1000) + tone(1500) + silence(1000)
    approx(detect_pieces(audio, **PARAMS), [(800, 3200), (3800, 5700)])


def test_audio_starting_with_voice_keeps_first_phrase():
    audio = tone(2000) + silence(1000) + tone(1500)
    approx(detect_pieces(audio, **PARAMS), [(0, 2200), (2800, 4500)])


def test_no_silence_is_one_piece():
    approx(detect_pieces(tone(3000), **PARAMS), [(0, 3000)])


def test_only_silence_is_nothing():
    assert detect_pieces(silence(3000), **PARAMS) == []


def test_short_pause_does_not_split():
    audio = silence(1000) + tone(1000) + silence(500) + tone(1000) + silence(1000)
    approx(detect_pieces(audio, **PARAMS), [(800, 3700)])
    approx(detect_pieces(audio, padding=100, min_silence_len=400, silence_thresh=-40),
           [(900, 2100), (2400, 3600)])


def test_detect_pieces_in_range():
    audio = silence(1000) + tone(1000) + silence(500) + tone(1000) + silence(1000) + tone(2000) + silence(1000)
    whole = detect_pieces(audio, **PARAMS)
    approx(whole, [(800, 3700), (4300, 6700)])

    # re-split only the first segment with a shorter pause; the positions stay absolute
    start, end = whole[0]
    pieces = detect_pieces_in_range(audio, start, end, padding=100, min_silence_len=400, silence_thresh=-40)
    approx(pieces, [(800, 2100), (2400, 3700)])
    assert pieces[0][0] == start and pieces[-1][1] == end


def test_split_params_env(monkeypatch):
    monkeypatch.setenv('MIN_SILENCE_LEN_MS', '650')
    monkeypatch.delenv('PADDING_MS', raising=False)
    monkeypatch.delenv('SILENCE_THRESHOLD_DB', raising=False)
    assert split_params() == {"min_silence_len": 650, "padding": 200, "silence_thresh": -40}
    assert split_params(300, 50, -35) == {"min_silence_len": 300, "padding": 50, "silence_thresh": -35}


def test_split_file_resets_segments(tmp_path):
    metadata = SegmentManager(str(tmp_path / 'lb_test.mp3'))
    metadata.segments = [{"start": 0, "end": 10, "text": "old"}]
    audio = silence(1000) + tone(2000) + silence(1000)
    split_file(audio, metadata, **PARAMS)
    assert len(metadata.segments) == 1
    assert metadata.segments[0]['text'] == ''


def test_find_pauses_longest_first():
    audio = tone(1000) + silence(300) + tone(1000) + silence(600) + tone(1000) + silence(500)
    pauses = find_pauses(audio, 0, len(audio))
    approx(pauses, [(2300, 2900), (1000, 1300)])  # the trailing silence touches the edge, so it is not a pause


def test_pick_cut_auto():
    audio = silence(500) + tone(1000) + silence(300) + tone(1000) + silence(700) + tone(1000) + silence(500)
    first_end, second_start = pick_cut(audio, 400, 4600, padding=200)
    assert abs(first_end - 3000) <= 30 and abs(second_start - 3300) <= 30

    # a pause shorter than two paddings is cut in the middle
    first_end, second_start = pick_cut(audio, 400, 2700, padding=200)
    assert first_end == second_start and abs(first_end - 1650) <= 30

    assert pick_cut(tone(2000), 0, 2000) is None


def test_pick_cut_at_cursor():
    audio = silence(500) + tone(1000) + silence(300) + tone(1000) + silence(700) + tone(1000) + silence(500)
    # the cursor is in (or right next to) a pause: snap to it
    first_end, second_start = pick_cut(audio, 400, 4600, at_ms=2900, padding=200)
    assert abs(first_end - 3000) <= 30 and abs(second_start - 3300) <= 30
    # the cursor is in the middle of speech: cut exactly there
    assert pick_cut(audio, 400, 4600, at_ms=2200, padding=200) == (2200, 2200)
    assert pick_cut(tone(2000), 0, 2000, at_ms=900) == (900, 900)


def noise(ms, volume):
    return WhiteNoise().to_audio_segment(duration=ms, volume=volume)


@pytest.mark.parametrize("frame_rate, channels", [(44100, 1), (22050, 2), (48000, 1)])
def test_fast_detect_silence_equals_pydub(frame_rate, channels):
    audio = (silence(700) + tone(900) + noise(450, -50) + tone(300) + noise(60, -20) + silence(1300)
             + noise(900, -38) + tone(1111) + silence(333) + tone(205) + silence(1207))
    audio = audio.set_frame_rate(frame_rate).set_channels(channels)
    for min_silence_len in (100, 333, 800, 1000):
        for silence_thresh in (-50, -40, -30):
            expected = pydub_detect_silence(audio, min_silence_len, silence_thresh)
            assert detect_silence(audio, min_silence_len, silence_thresh) == expected, (min_silence_len, silence_thresh)
    assert detect_silence(silence(100), 500, -40) == []
    assert detect_silence(tone(1000), 500, -40) == []


def test_suggest_min_silence_len():
    # pauses inside phrases are 150-300 ms, between phrases 900-1400 ms
    audio = silence(500)
    for inner, outer in [(150, 900), (300, 1400), (200, 1000), (250, 1200)]:
        audio += tone(700) + silence(inner) + tone(700) + silence(outer)
    suggestion, lengths = suggest_min_silence_len(audio)
    assert len(lengths) == 7  # the last silence touches the end
    assert 300 < suggestion < 900
    assert len(detect_pieces(audio, padding=100, min_silence_len=suggestion, silence_thresh=-40)) == 4

    assert suggest_min_silence_len(tone(3000))[0] is None
