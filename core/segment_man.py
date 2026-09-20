import json
import os.path
from typing import Dict, List

from core.audio_utils import mp3_length_seconds
from core.furigana import convert_ruby_to_parenthesis


class SegmentManager:
    VERSION = 3
    POSTFIX = "_segments.json"

    @classmethod
    def segments_filename(cls, original_filename):
        if original_filename.endswith(cls.POSTFIX):
            return original_filename
        return original_filename + cls.POSTFIX

    def __init__(self, filename):
        self._filename = filename
        self.segments: List[Dict] = []
        self.title = os.path.basename(filename)
        self.length = 0

    def get_digest(self):
        digest_str = ""
        for segment in self.segments:
            digest_str += segment.get("original_text") or segment.get("text", "") or ""
        return digest_str

    @property
    def sorted_segments(self):
        return self.segments

    @property
    def original_sentences(self):
        return [
            segment.get('original_text', segment.get('text', ''))
            for segment in self.segments
        ]

    @property
    def all_has_original_text(self):
        return all('original_text' in segment for segment in self.segments)

    @property
    def original_filename(self):
        return self._filename

    def save(self, save_as=None):
        json_filename = self.segments_filename(save_as or self._filename)
        with open(json_filename, "w") as json_file:
            # noinspection PyTypeChecker
            json.dump({
                "filename": os.path.basename(self._filename),
                "title": self.title or os.path.basename(self._filename),
                "total_segments": len(self.segments),
                "segments": self.segments,
                "length": self.length or mp3_length_seconds(self._filename),
                "version": self.VERSION,
            }, json_file, ensure_ascii=False, indent=4)
        print(f"Non-silent segments saved to {json_filename}")

    def load(self):
        json_filename = self.segments_filename(self._filename)
        self.segments = []
        try:
            try:
                with open(json_filename, "r") as json_file:
                    data = json.load(json_file)
                    version = data.get('version', 1)
                    if version not in (2, 3):
                        raise ValueError(f"Unsupported version: {version}")

                    self.title = data.get('title') or self.title
                    self.length = data.get('length') or 0

                    segments = data['segments']
                    if isinstance(segments, dict):
                        self.segments = list(segments.values())
                    else:
                        self.segments = segments
                    self.sort()

                print(f"Non-silent segments loaded from {json_filename} ({len(self.segments)} segments)")
                return True
            except json.JSONDecodeError:
                print(f"Failed to load JSON file: {json_filename}")
                return False
        except FileNotFoundError:
            print(f"Non-silent segments JSON file not found: {json_filename}")
            return False

    def sort(self):
        self.segments.sort(key=lambda x: x['start'])

    @property
    def segments_without_text(self):
        return [v for v in self.segments if not v['text']]

    def clear(self):
        self.segments.clear()

    def convert_ruby_to_parenthesis(self):
        for k, v in self.segments:
            text = v['text']
            v['text'] = convert_ruby_to_parenthesis(text)
            print(f"Converted '{text}' to '{v['text']}'")

    def update_texts(self, new_sentences):
        if len(new_sentences) != len(self.segments):
            raise ValueError("Number of sentences does not match number of segments!")

        for i, new_text in enumerate(new_sentences):
            self.set_furigana(i, new_text)

    def _check_index(self, i):
        if not 0 <= i < len(self.segments):
            raise IndexError("Segment index out of range")

    def set_text(self, i, new_text):
        self._check_index(i)
        self.segments[i]['text'] = new_text

    def set_original_text(self, i, new_text):
        self._check_index(i)
        seg = self.segments[i]
        # original_text marks a segment as furiganated, so never create it here
        if 'original_text' not in seg:
            raise ValueError("Segment is not furiganated, edit its text instead")
        seg['original_text'] = new_text

    def set_furigana(self, i, furigana_text):
        self._check_index(i)
        seg = self.segments[i]
        seg.setdefault("original_text", seg["text"])
        seg['text'] = furigana_text

    def drop_furigana(self, i):
        self._check_index(i)
        seg = self.segments[i]
        if 'original_text' in seg:
            seg['text'] = seg.pop('original_text')

    def set_segments(self, segments):
        self.segments = [
            {
                "start": start,
                "end": end,
                "text": "",
            } for start, end in segments
        ]
        self.sort()

    def join_segments(self, id1, id2):
        self._check_index(id1)
        self._check_index(id2)

        if id1 > id2:
            id1, id2 = id2, id1

        if id2 - id1 != 1:
            raise ValueError("Segments to join must be adjacent")

        segment1 = self.segments[id1]
        segment2 = self.segments[id2]

        new_segment = {
            "start": segment1['start'],
            "end": segment2['end'],
            "text": f"{segment1['text']} {segment2['text']}".strip(),
        }

        if 'original_text' in segment1 or 'original_text' in segment2:
            original1 = segment1.get('original_text', segment1['text'])
            original2 = segment2.get('original_text', segment2['text'])
            new_segment['original_text'] = f"{original1} {original2}".strip()

        self.segments[id1] = new_segment
        del self.segments[id2]
        self.sort()

    def split_segment(self, i, at_ms, resume_ms=None):
        """Cut a segment in two: [start, at_ms] and [resume_ms, end]; resume_ms > at_ms drops the pause between"""
        self._check_index(i)
        seg = self.segments[i]
        at_ms = int(at_ms)
        resume_ms = at_ms if resume_ms is None else int(resume_ms)
        if not seg['start'] < at_ms <= resume_ms < seg['end']:
            raise ValueError("Split point must be inside the segment")

        # the texts stay in the first half; the second one is left for transcription
        second = {
            "start": resume_ms,
            "end": seg['end'],
            "text": "",
        }
        seg['end'] = at_ms
        self.segments.insert(i + 1, second)

    def set_bounds(self, i, start, end):
        self._check_index(i)
        start, end = int(start), int(end)
        if start < 0 or start >= end:
            raise ValueError("Invalid segment bounds")
        if i > 0 and start < self.segments[i - 1]['end']:
            raise ValueError("Segment overlaps the previous one")
        if i + 1 < len(self.segments) and end > self.segments[i + 1]['start']:
            raise ValueError("Segment overlaps the next one")

        self.segments[i]['start'] = start
        self.segments[i]['end'] = end

    def delete_segment(self, i):
        self._check_index(i)
        del self.segments[i]

    def replace_segment(self, i, pieces):
        """Replace segment i with new empty segments, e.g. after re-splitting only its range"""
        self._check_index(i)
        if not pieces:
            raise ValueError("No pieces to replace the segment with")

        self.segments[i:i + 1] = [
            {
                "start": start,
                "end": end,
                "text": "",
            } for start, end in pieces
        ]
        self.sort()
