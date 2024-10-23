import json
import os.path

from core.furigana import convert_ruby_to_parenthesis
from core.splitter import load_audio_file


class SegmentManager:
    @staticmethod
    def segments_filename(original_filename):
        return original_filename + "_segments.json"

    def __init__(self, filename):
        self._filename = filename
        self.segments = {}
        self.title = os.path.basename(filename)
        self.length = 0

    @property
    def audio(self):
        return load_audio_file(self._filename)

    @property
    def sorted_segments(self):
        return sorted(self.segments.values(), key=lambda x: x['start'])

    @property
    def original_filename(self):
        return self._filename

    def save(self, save_as=None):
        json_filename = self.segments_filename(save_as or self._filename)
        with open(json_filename, "w") as json_file:
            json.dump({
                "filename": os.path.basename(self._filename),
                "title": self.title or os.path.basename(self._filename),
                "total_segments": len(self.segments),
                "segments": self.segments,
                "length": self.length or len(self.audio) / 1000,
                "version": 2
            }, json_file, ensure_ascii=False, indent=4)
        print(f"Non-silent segments saved to {json_filename}")

    def load(self):
        json_filename = self.segments_filename(self._filename)
        self.segments = {}
        try:
            try:
                with open(json_filename, "r") as json_file:
                    data = json.load(json_file)
                    version = data.get('version', 1)
                    if version != 2:
                        raise ValueError(f"Unsupported version: {version}")

                    self.segments = data['segments']

                print(f"Non-silent segments loaded from {json_filename}")
                return True
            except json.JSONDecodeError:
                print(f"Failed to load JSON file: {json_filename}")
                return False
        except FileNotFoundError:
            print(f"Non-silent segments JSON file not found: {json_filename}")
            return False

    @staticmethod
    def segment_key(start, end):
        return f'{start:08}..{end:08}'

    def set_segment(self, start, end, text=''):
        self.segments[self.segment_key(start, end)] = {
            'start': start,
            'end': end,
            'text': text
        }

    def does_segment_exist(self, start, end):
        return self.segment_key(start, end) in self.segments

    @property
    def segments_without_text(self):
        return {k: v for k, v in self.segments.items() if not v['text']}

    def clear(self):
        self.segments.clear()

    def convert_ruby_to_parenthesis(self):
        for k, v in self.segments.items():
            text = v['text']
            v['text'] = convert_ruby_to_parenthesis(text)
            print(f"Converted '{text}' to '{v['text']}'")

    def update_texts(self, new_sentences):
        if len(new_sentences) != len(self.segments):
            raise ValueError("Number of sentences does not match number of segments!")

        for segment, new_text in zip(self.sorted_segments, new_sentences):
            segment['text'] = new_text
