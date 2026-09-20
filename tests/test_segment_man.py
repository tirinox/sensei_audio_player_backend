import json
import os

import pytest

from core.segment_man import SegmentManager


def make_seg(tmp_path, segments):
    seg = SegmentManager(os.path.join(tmp_path, 'lb_test.mp3'))
    seg.length = 10.0  # so that save() doesn't call ffprobe
    seg.segments = segments
    return seg


def plain(start, end, text):
    return {"start": start, "end": end, "text": text}


def furi(start, end, text, original):
    return {"start": start, "end": end, "text": text, "original_text": original}


def test_save_load_keeps_title_and_length(tmp_path):
    seg = make_seg(tmp_path, [plain(0, 1000, 'あ')])
    seg.title = 'Custom title'
    seg.save()

    loaded = SegmentManager(seg.original_filename)
    assert loaded.load()
    assert loaded.title == 'Custom title'
    assert loaded.length == 10.0
    assert loaded.segments == [plain(0, 1000, 'あ')]


def test_load_v2_dict(tmp_path):
    seg = make_seg(tmp_path, [])
    with open(seg.segments_filename(seg.original_filename), 'w') as f:
        json.dump({"version": 2, "segments": {"b": plain(500, 900, 'い'), "a": plain(0, 400, 'あ')}}, f)
    assert seg.load()
    assert [s['text'] for s in seg.segments] == ['あ', 'い']


def test_set_text_does_not_mark_as_furiganated(tmp_path):
    seg = make_seg(tmp_path, [plain(0, 1000, 'あ')])
    seg.set_text(0, 'い')
    assert seg.segments[0] == plain(0, 1000, 'い')
    assert not seg.all_has_original_text


def test_set_original_text_only_for_furiganated(tmp_path):
    seg = make_seg(tmp_path, [plain(0, 1000, 'あ'), furi(1000, 2000, '[日](ひ)', '日')])
    with pytest.raises(ValueError):
        seg.set_original_text(0, 'い')
    seg.set_original_text(1, '火')
    assert seg.segments[1]['original_text'] == '火'
    assert seg.segments[1]['text'] == '[日](ひ)'


def test_set_and_drop_furigana(tmp_path):
    seg = make_seg(tmp_path, [plain(0, 1000, '日')])
    seg.set_furigana(0, '[日](ひ)')
    assert seg.segments[0] == furi(0, 1000, '[日](ひ)', '日')

    # furiganating again keeps the first plain text
    seg.set_furigana(0, '[日](にち)')
    assert seg.segments[0] == furi(0, 1000, '[日](にち)', '日')

    seg.drop_furigana(0)
    assert seg.segments[0] == plain(0, 1000, '日')


def test_update_texts(tmp_path):
    seg = make_seg(tmp_path, [plain(0, 1000, '日'), plain(1000, 2000, '火')])
    with pytest.raises(ValueError):
        seg.update_texts(['[日](ひ)'])
    seg.update_texts(['[日](ひ)', '[火](ひ)'])
    assert seg.all_has_original_text
    assert seg.original_sentences == ['日', '火']


def test_join_plain(tmp_path):
    seg = make_seg(tmp_path, [plain(0, 1000, 'あ'), plain(1200, 2000, 'い'), plain(2500, 3000, 'う')])
    seg.join_segments(2, 1)
    assert seg.segments == [plain(0, 1000, 'あ'), plain(1200, 3000, 'い う')]


def test_join_keeps_original_text(tmp_path):
    seg = make_seg(tmp_path, [furi(0, 1000, '[日](ひ)', '日'), furi(1200, 2000, '[火](ひ)', '火')])
    seg.join_segments(0, 1)
    assert seg.segments == [furi(0, 2000, '[日](ひ) [火](ひ)', '日 火')]
    assert seg.all_has_original_text


def test_join_furiganated_with_plain(tmp_path):
    seg = make_seg(tmp_path, [furi(0, 1000, '[日](ひ)', '日'), plain(1200, 2000, '火')])
    seg.join_segments(0, 1)
    assert seg.segments == [furi(0, 2000, '[日](ひ) 火', '日 火')]


def test_join_errors(tmp_path):
    seg = make_seg(tmp_path, [plain(0, 1000, 'あ'), plain(1200, 2000, 'い'), plain(2500, 3000, 'う')])
    with pytest.raises(ValueError):
        seg.join_segments(0, 2)
    with pytest.raises(IndexError):
        seg.join_segments(2, 3)
    with pytest.raises(IndexError):
        seg.join_segments(-1, 0)


def test_split_segment(tmp_path):
    seg = make_seg(tmp_path, [furi(0, 1000, '[日](ひ)', '日'), plain(1200, 2000, 'い')])
    seg.split_segment(0, 400)
    assert seg.segments == [furi(0, 400, '[日](ひ)', '日'), plain(400, 1000, ''), plain(1200, 2000, 'い')]
    assert seg.segments_without_text == [plain(400, 1000, '')]

    for bad in (0, 400, 1000, 5000):
        with pytest.raises(ValueError):
            seg.split_segment(0, bad)


def test_split_segment_drops_the_pause(tmp_path):
    seg = make_seg(tmp_path, [plain(0, 3000, 'あ')])
    seg.split_segment(0, 1200, 1700)
    assert seg.segments == [plain(0, 1200, 'あ'), plain(1700, 3000, '')]
    for at_ms, resume_ms in [(1000, 900), (1000, 1200), (500, 1200)]:
        with pytest.raises(ValueError):
            seg.split_segment(0, at_ms, resume_ms)


def test_set_bounds(tmp_path):
    seg = make_seg(tmp_path, [plain(0, 1000, 'あ'), plain(1200, 2000, 'い'), plain(2500, 3000, 'う')])
    seg.set_bounds(1, 1000, 2500)  # touching the neighbours is fine
    assert seg.segments[1] == plain(1000, 2500, 'い')

    for start, end in [(999, 2000), (1200, 2501), (1500, 1500), (1600, 1500)]:
        with pytest.raises(ValueError):
            seg.set_bounds(1, start, end)
    with pytest.raises(ValueError):
        seg.set_bounds(0, -5, 500)
    assert seg.segments[1] == plain(1000, 2500, 'い')

    seg.set_bounds(2, 2600, 99000)  # the last one is limited only from the left
    assert seg.segments[2] == plain(2600, 99000, 'う')


def test_delete_segment(tmp_path):
    seg = make_seg(tmp_path, [plain(0, 1000, 'あ'), plain(1200, 2000, 'い')])
    seg.delete_segment(0)
    assert seg.segments == [plain(1200, 2000, 'い')]
    with pytest.raises(IndexError):
        seg.delete_segment(1)


def test_replace_segment(tmp_path):
    seg = make_seg(tmp_path, [plain(0, 1000, 'あ'), furi(1200, 3000, '[日](ひ)', '日'), plain(3500, 4000, 'う')])
    seg.replace_segment(1, [(1200, 1900), (2100, 3000)])
    assert seg.segments == [
        plain(0, 1000, 'あ'), plain(1200, 1900, ''), plain(2100, 3000, ''), plain(3500, 4000, 'う'),
    ]
    with pytest.raises(ValueError):
        seg.replace_segment(1, [])


def test_digest_uses_plain_text(tmp_path):
    seg = make_seg(tmp_path, [furi(0, 1000, '[日](ひ)', '日'), plain(1200, 2000, 'い')])
    assert seg.get_digest() == '日い'
