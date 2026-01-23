from pydub.playback import play

from core.audio_utils import load_audio_file
from core.segment_man import SegmentManager


class Player:
    def __init__(self, audio_file):
        self.audio = load_audio_file(audio_file)
        self.metadata = SegmentManager(audio_file)
        self.ready = self.metadata.load()
        self.current_segment_idx = 0

    @property
    def total_segments(self):
        return len(self.metadata.segments)

    def __getitem__(self, item):
        seg = self.metadata.sorted_segments[item]
        start, end = int(seg['start']), int(seg['end'])
        segment = self.audio[start:end]
        return start, end, segment

    def play_segment(self, idx):
        start, end, segment = self[idx]
        print(f"[{idx:02} / {self.total_segments:02}] Playing segment "
              f"from {start / 1000:.2f} seconds to {end / 1000:.2f} seconds...")
        play(segment)

    def play_current_segment(self):
        self.play_segment(self.current_segment_idx)

    def play_next_segment(self):
        self.shift(1)
        self.play_current_segment()

    def play_previous_segment(self):
        self.shift(-1)
        self.play_current_segment()

    def shift(self, direction=1):
        self.current_segment_idx += direction
        self.current_segment_idx %= self.total_segments
