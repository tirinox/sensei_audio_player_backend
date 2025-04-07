import json
import os.path

from core.furigana import convert_ruby_to_parenthesis
from core.splitter import load_audio_file


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
    def audio(self):
        return load_audio_file(self._filename)

    @property
    def sorted_segments(self):
        return self.segments

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
                "length": self.length or len(self.audio) / 1000,
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

                print(f"Non-silent segments loaded from {json_filename}")
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
            segment['text'] = new_text

    def set_segments(self, segments):
        self.segments = segments
        self.sort()
