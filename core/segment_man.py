import json
import os.path

from core.furigana import convert_ruby_to_parenthesis
from core.splitter import load_audio_file, mp3_length_seconds


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
        self.segments = []
        self.title = os.path.basename(filename)
        self.length = 0

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

        for segment, new_text in zip(self.sorted_segments, new_sentences):
            segment.setdefault("original_text", segment["text"])
            segment['text'] = new_text

    def set_text(self, i, new_text):
        seg = self.segments[i]
        seg.setdefault("original_text", new_text)
        seg['text'] = new_text

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
        if id1 >= len(self.segments) or id2 >= len(self.segments):
            raise IndexError("Segment index out of range")

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

        self.segments[id1] = new_segment
        del self.segments[id2]
        self.sort()
