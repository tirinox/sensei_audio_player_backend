import re

import pytest

from core.correction_neural import CorrectionNeural, correct_segments
from core.segment_man import SegmentManager, carry_furigana, strip_furigana


class ScriptedCorrector(CorrectionNeural):
    """No network: the 'LLM' applies the given replacements to the numbered lines it is asked to correct"""

    def __init__(self, replacements=None, answer=None):
        self.prompt = 'PROMPT'
        self.replacements = replacements or {}
        self.answer = answer
        self.requests = []

    def _request_ai(self, prompt, temperature=0.7):
        self.requests.append(prompt)
        if self.answer is not None:
            return self.answer
        lines = [line for line in prompt.split('Lines to correct:\n')[1].splitlines() if re.match(r'\d+\. ', line)]
        for old, new in self.replacements.items():
            lines = [line.replace(old, new) for line in lines]
        return '\n'.join(lines)


def make_seg(tmp_path, segments):
    seg = SegmentManager(str(tmp_path / 'lb_test.mp3'))
    seg.length = 10.0
    seg.segments = segments
    return seg


def test_correct_keeps_count_and_order():
    corrector = ScriptedCorrector({'絵を書く': '絵を描く', '三人': '3人'})
    assert corrector.correct(['絵を書くのが好きです', '2', '三人で行きます。']) == ['絵を描くのが好きです', '2', '3人で行きます。']


def test_chunks_get_previous_sentences_as_context():
    corrector = ScriptedCorrector({'あ': 'ア'})
    corrector.CHUNK_SIZE, corrector.CONTEXT_SIZE = 3, 2
    sentences = [f'あ{n}。' for n in range(7)]
    assert corrector.correct(sentences) == [f'ア{n}。' for n in range(7)]
    assert len(corrector.requests) == 3
    assert 'for context only' not in corrector.requests[0]
    context = corrector.requests[1].split('Lines to correct:')[0]
    assert 'ア1。\nア2。' in context and 'ア0。' not in context  # corrected already, only the last two
    assert '1. あ3。' in corrector.requests[1]


def test_broken_answers():
    with pytest.raises(ValueError):
        ScriptedCorrector(answer='1. あ。').correct(['あ。', 'い。'])
    # the LLM answered instead of correcting: the line stays as it was
    chatty = ScriptedCorrector(answer='1. これは正しい文です。変更する必要はありません。\n2. い。')
    assert chatty.correct(['あ。', 'い']) == ['あ。', 'い。']


def test_correct_one_uses_neighbours():
    corrector = ScriptedCorrector({'書': '描'})
    sentences = [f'{n}を書く。' for n in range(10)]
    assert corrector.correct_one(sentences, 5, window=2) == '5を描く。'
    assert '1. 3を書く。' in corrector.requests[0] and '5. 7を書く。' in corrector.requests[0]
    assert '8を書く' not in corrector.requests[0]
    assert 'error in line 3 ' in corrector.requests[0]  # the suspected line is pointed out
    assert corrector.correct_one(sentences, 0, window=2) == '0を描く。'


def test_correct_segments(tmp_path):
    seg = make_seg(tmp_path, [
        {"start": 0, "end": 1000, "text": "[絵](え)を[書](か)く。", "original_text": "絵を書く。"},
        {"start": 1000, "end": 2000, "text": ""},
        {"start": 2000, "end": 3000, "text": "手紙を書く。"},
        {"start": 3000, "end": 4000, "text": "[絵](え)を[書](か)いた。", "original_text": "絵を書いた。", "raw_text": "絵を書いた。"},
    ])
    checked, changed = correct_segments(seg, ScriptedCorrector({'絵を書': '絵を描'}))
    assert (checked, changed) == (2, 1)

    # changed: furigana is outdated and dropped, the text before is kept
    assert seg.segments[0] == {"start": 0, "end": 1000, "text": "絵を描く。", "raw_text": "絵を書く。"}
    assert seg.segments[1] == {"start": 1000, "end": 2000, "text": ""}
    # not changed: only marked as checked
    assert seg.segments[2] == {"start": 2000, "end": 3000, "text": "手紙を書く。", "raw_text": "手紙を書く。"}
    # corrected before: not touched, though the LLM would change it
    assert seg.segments[3]['original_text'] == '絵を書いた。'

    assert correct_segments(seg, ScriptedCorrector({'絵を書': '絵を描'})) == (0, 0)
    assert correct_segments(seg, ScriptedCorrector({'絵を書': '絵を描'}), redo=True) == (3, 1)
    assert seg.segments[3] == {"start": 3000, "end": 4000, "text": "絵を描いた。", "raw_text": "絵を書いた。"}


def test_revert_and_join(tmp_path):
    seg = make_seg(tmp_path, [
        {"start": 0, "end": 1000, "text": "[絵](え)を[描](か)く。", "original_text": "絵を描く。", "raw_text": "絵を書く。"},
        {"start": 1000, "end": 2000, "text": "はい。", "raw_text": "はい。"},
        {"start": 2000, "end": 3000, "text": "いいえ。"},
    ])
    seg.revert_correction(0)
    assert seg.segments[0] == {"start": 0, "end": 1000, "text": "絵を書く。", "raw_text": "絵を書く。"}
    assert seg.segments_without_correction == [2]  # a reverted one is not corrected again

    seg.join_segments(0, 1)
    assert seg.segments[0]['raw_text'] == '絵を書く。 はい。'
    seg.join_segments(0, 1)
    assert 'raw_text' not in seg.segments[0]  # one half was never corrected


def test_legacy_markup_in_original_text(tmp_path):
    # old files: original_text is a copy of the furiganated text
    markup = "[絵](え)を[書](か)く。"
    seg = make_seg(tmp_path, [
        {"start": 0, "end": 1000, "text": markup, "original_text": markup},
        {"start": 1000, "end": 2000, "text": "[今日](きょう)は[3人](さんにん)です。", "original_text": "[今日](きょう)は[3人](さんにん)です。"},
    ])
    assert seg.plain_text(0) == "絵を書く。"

    corrector = ScriptedCorrector({'絵を書': '絵を描'})
    assert correct_segments(seg, corrector) == (2, 1)
    assert '1. 絵を書く。' in corrector.requests[0] and '[' not in corrector.requests[0].split('Lines to correct:')[1]
    assert seg.segments[0] == {"start": 0, "end": 1000, "text": "絵を描く。", "raw_text": "絵を書く。"}
    # nothing to fix: the furigana made by hand stays
    assert seg.segments[1]['text'] == "[今日](きょう)は[3人](さんにん)です。"
    assert seg.segments[1]['raw_text'] == "今日は3人です。"


def test_carry_furigana():
    markup = "[今](いま)[相撲](すもう)は[1](いち)[年](ねん)に[6回](ろっかい) あります"
    assert carry_furigana(markup, "今、相撲は1年に6回あります。") == \
        "[今](いま)、[相撲](すもう)は[1](いち)[年](ねん)に[6回](ろっかい)あります。"
    assert carry_furigana(markup, strip_furigana(markup)) == markup
    assert carry_furigana("プロ・スポーツです。", "プロスポーツです！") == "プロスポーツです！"

    # a word was changed, or the change is inside a group: the furigana has to be made again
    assert carry_furigana("[絵](え)を[書](か)く。", "絵を描く。") is None
    assert carry_furigana("[1,300](せんさんびゃく)[年](ねん)", "1300年") is None
    assert carry_furigana("ごはんを[食](た)べる", "ご飯を食べる") is None


def test_punctuation_only_correction_keeps_furigana(tmp_path):
    seg = make_seg(tmp_path, [
        {"start": 0, "end": 1000, "text": "[今](いま)[相撲](すもう)を[見](み)る", "original_text": "[今](いま)[相撲](すもう)を[見](み)る"},
    ])
    assert seg.set_correction(0, "今、相撲を見る。")
    assert seg.segments[0] == {"start": 0, "end": 1000, "text": "[今](いま)、[相撲](すもう)を[見](み)る。",
                               "original_text": "今、相撲を見る。", "raw_text": "今相撲を見る"}
