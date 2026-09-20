import os

from core.furigana_neural import FuriganaNeural, process_numbered_list

PROMPT_CORRECTION = """
You are a careful editor of Japanese transcripts. The numbered lines below are consecutive phrases of ONE audio recording
from a Japanese course for learners at JLPT N3-N2 level. They were produced by automatic speech recognition (Whisper),
so they contain recognition errors. Correct each line so that it is an accurate, natural and easy to read written form
of what was actually SAID. Use the meaning of the whole recording, not only of the single line.

What to fix:

1. Wrong kanji and homophones. THIS IS THE MOST IMPORTANT PART. Speech recognition writes what it hears, so it often
   picks a word that sounds the same but means something else. First read all the lines and understand what the
   recording is about. Then go through every noun, verb and adjective written in kanji and ask: does THIS word make sense
   here, in this topic? If it does not, and a word with the same pronunciation does, replace it.
   Examples: 手紙をかく → 書く, but 絵 / 似顔絵 / 漫画 / 地図をかく → 描く; 性格 (character) / 正確 (accurate);
   暑い (weather) / 熱い (things) / 厚い (thick); 聞く / 効く / 利く; 早い (early) / 速い (fast); 会う / 合う;
   変える / 帰る / 買える; 以外 / 意外; 機会 / 機械; 感心 / 関心; 自信 / 自身 / 地震; 公園 / 講演; 最近 / 細菌.
   A word that the neighbouring lines use in the right spelling is a strong hint (正確な似顔絵 ... 性格で → 正確で).
   Fix misheard words and names only when the context makes the intended word clear.

2. Kanji vs kana, as in a modern textbook for this level.
   - Words that are normally written in kana stay in kana: こと, もの, とき, ところ, ため, わけ, はず, よう, ほう, できる,
     ある, いる, なる, いただく, ください, いろいろ, たくさん, ちょっと, とても, もう, まだ, など, ほど, くらい, まで, ながら,
     また, しかし, そして, それから, あまり, きれい, おいしい, うれしい, ありがとう, すみません, grammatical auxiliaries
     (〜てみる, 〜ておく, 〜てくる, 〜ていく, 〜てしまう, 〜ていただく), etc.
   - Words that are normally written in kanji are written in kanji (今日, 学校, 食べる, 時間, 自分, 必要 ...).
   - Do NOT use rare or difficult kanji (beyond N2 / outside common jōyō use). Write such words in hiragana:
     綺麗→きれい, 沢山→たくさん, 筈→はず, 或る→ある, 暫く→しばらく, 殆ど→ほとんど, 勿論→もちろん, 宜しく→よろしく,
     有難う→ありがとう, 出来る→できる, 下さい→ください, 御飯→ご飯, 貴方→あなた, 何故→なぜ, 是非→ぜひ.
   - Loanwords and foreign names in katakana.

3. Numbers. Quantities, counters, times, dates, ages, prices, percentages: half-width Arabic digits
   (3人, 10時半, 2000円, 5月3日, 20歳, 100%, 1時間, 2番目, 第1課). Keep kanji in fixed words where the number is not
   a quantity (一緒, 一番, 一生懸命, 一般, 一部, 一方, 唯一, 第一印象, 二度と, 万一, 四季, 十分 "enough") and in the native
   counters 一つ…九つ, 一人, 二人.

4. Punctuation, for comfortable reading, following the meaning and the rhythm of speech.
   - 、 between clauses and after long topics, not after every word.
   - Put 、 after a conjunction or a sentence adverb that opens a sentence or a clause, whenever it is followed by
     more text: でも、 しかし、 だが、 けれども、 ところが、 それでも、 もちろん、 だから、 ですから、 それで、 そこで、
     そして、 それから、 それに、 また、 さらに、 しかも、 すると、 つまり、 たとえば、 実は、 ところで、 さて、 では、
     一方、 ただ、 ただし、 なお、 やはり、 確かに、 まず、 次に、 最後に、 and similar words.
     Examples: でも明るい色より暗い色の方が好きです。 → でも、明るい色より暗い色の方が好きです。
     もちろん危険だけではありません。 → もちろん、危険だけではありません。
     This rule is not a matter of style: add the comma even if the rest of the line needs no changes.
     In the middle of a sentence, after a topic, the comma goes BEFORE such a word, not after it:
     赤のイメージはもちろん危険だけではありません。 → 赤のイメージは、もちろん危険だけではありません。
     (〜はもちろん、 would read as the pattern "not to mention ~" and change the meaning.)
     Do not add it when the word is not used as a conjunction (また会いましょう, まず第一に are fine as they are),
     or when the word is the whole line.
   - Every line that is a sentence or a phrase must END with a punctuation mark: 。 or ？ or ！ (or 」 if it closes a quote).
     Questions end with ？ when it helps reading, plain か。 is fine too.
   - Quoted speech, titles and words under discussion in 「」.
   - Full-width Japanese punctuation only (、。？！「」), no spaces between Japanese words.
   - A line that is only a label or a number ("1", "2.", "A", "練習A", "例") is left exactly as it is.

What you must NOT do:

- Do not paraphrase, do not improve style or grammar, do not make it more polite, do not add or remove words,
  fillers or repetitions. The text must still match the audio word for word. The speaker's mistakes stay.
- Never insert, delete or replace particles (は, が, を, に, の, で, と, も, へ, から, まで ...) and never change verb forms.
  If read aloud, your line must sound exactly like the original line. Changing only the spelling is the whole job.
  Replace the misspelled word itself and nothing around it: 性格で → 正確で (NOT 正確に), プロ・スポーツ → プロスポーツ
  (NOT プロのスポーツ).
- Do not merge, split, reorder, skip or add lines. Line N of the output is the corrected line N of the input.
- Do not add furigana, readings, translations, comments or explanations.
- If a line is already correct, return it unchanged. When unsure about punctuation or kana/kanji style, keep the
  original. But a word that makes no sense in its context, while its homophone does, is an error: fix it.

Output: exactly the same numbered list (same numbers, same count of lines), corrected text only.
"""

CONTEXT_HEADER = "Previous phrases of the same recording, for context only. Do NOT include them in the output:"
TASK_HEADER = "Lines to correct:"
FOCUS_NOTE = "The user suspects a recognition error in line {n} (most likely a wrong homophone). Check that line with special care."


class CorrectionNeural(FuriganaNeural):
    """Same LLM client as for furigana, another prompt: fixes speech recognition errors in the plain transcript"""

    CHUNK_SIZE = 25  # sentences per request, so the answer fits into max_tokens
    CONTEXT_SIZE = 4  # previous sentences shown to the next chunk
    TEMPERATURE = 0.2

    def __init__(self, api_url, api_key, model, prompt=PROMPT_CORRECTION):
        super().__init__(api_url, api_key, model, prompt=prompt)

    def correct(self, sentences):
        """Corrected sentences, same count and order. A line the LLM broke (empty, way shorter or longer) stays as it was"""
        result = []
        for chunk_start in range(0, len(sentences), self.CHUNK_SIZE):
            chunk = sentences[chunk_start:chunk_start + self.CHUNK_SIZE]
            context = result[max(0, chunk_start - self.CONTEXT_SIZE):chunk_start]
            result.extend(self._correct_chunk(chunk, context))
        return result

    def correct_one(self, sentences, index, window=12):
        """Correct sentences[index]; its neighbours go along so the LLM sees the context (a few lines are not enough)"""
        first = max(0, index - window)
        corrected = self._correct_chunk(sentences[first:index + window + 1], [], focus=index - first + 1)
        return corrected[index - first]

    def _correct_chunk(self, chunk, context, focus=None):
        text = self.prompt + '\n\n'
        if context:
            text += CONTEXT_HEADER + '\n' + '\n'.join(context) + '\n\n'
        text += TASK_HEADER + '\n'
        for i, sentence in enumerate(chunk, 1):
            text += f"{i}. {sentence}\n"
        if focus:
            text += '\n' + FOCUS_NOTE.format(n=focus) + '\n'

        print("Requesting AI correction for", len(chunk), "sentences")
        response = self._request_ai(text, temperature=self.TEMPERATURE)

        lines = [line.strip() for line in process_numbered_list(response) if line.strip()]
        if len(lines) != len(chunk):
            raise ValueError(f"The LLM returned {len(lines)} lines for {len(chunk)} sentences")

        return [self._sane(old, new) for old, new in zip(chunk, lines)]

    @staticmethod
    def _sane(old, new):
        # a correction changes a few characters; anything else is the LLM rewriting or answering instead of correcting
        if not 0.6 <= len(new) / max(len(old), 1) <= 1.6 and abs(len(new) - len(old)) > 4:
            print(f"🛑Suspicious correction is ignored: '{old}' -> '{new}'")
            return old
        if old != new:
            print(f"Corrected: '{old}' -> '{new}'")
        return new


def correct_segments(seg, corrector, redo=False):
    """
    Correct the texts of a file (SegmentManager) and save it. Only the segments that were not corrected yet,
    unless redo. All sentences are sent anyway: the LLM needs the whole text for the context.
    Returns (checked, changed).
    """
    targets = [i for i, s in enumerate(seg.segments) if s.get('text')] if redo else seg.segments_without_correction
    if not targets:
        print("Nothing to correct")
        return 0, 0

    indices = [i for i, s in enumerate(seg.segments) if s.get('text')]
    corrected = corrector.correct([seg.plain_text(i) for i in indices])

    changed = 0
    for i, new_text in zip(indices, corrected):
        if i in targets and seg.set_correction(i, new_text):
            changed += 1
    seg.save()
    print(f"Correction: {len(targets)} segments checked, {changed} changed")
    return len(targets), changed
