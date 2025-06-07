import json
import os.path

from core.config import AUDIO_SOURCE_PATH
from core.file_man import get_all_mp3
from core.segment_man import SegmentManager


class AudioIndexer:
    def __init__(self, path, code: str):
        self.code = code.strip().upper()
        self.path = os.path.join(path, self.code)
        print("Indexer path:", self.path)
        self.files = []

    @property
    def index_file(self):
        return os.path.join(self.path, 'index.json')

    def get_all_mp3(self):
        print("Scanning for mp3 files in", self.path)
        return get_all_mp3(self.path)

    def scan_files(self):
        all_mp3 = self.get_all_mp3()
        if not all_mp3:
            print("No mp3 found! Check your path")
            return

        files = []

        for mp3_file in all_mp3:
            seg = SegmentManager(mp3_file)
            if seg.load():
                just_filename = os.path.basename(mp3_file)
                len_sec = len(seg.audio) / 1000  # this line loads the audio file into memory (slow)
                files.append({
                    "audio_file": just_filename,
                    "segment_file": seg.segments_filename(just_filename),
                    "n_segments": len(seg.segments),
                    "length": len_sec,
                    "title": just_filename,
                })

        return files

    def rebuild_index_and_save(self):
        old_titles = {}
        for mp3_file in self.files:
            if 'title' in mp3_file:
                old_titles[mp3_file['audio_file']] = mp3_file['title']

        self.files = self.scan_files()

        for mp3_file in self.files:
            if mp3_file['audio_file'] in old_titles:
                print(f"Restoring title for {mp3_file['audio_file']}")
                mp3_file['title'] = old_titles[mp3_file['audio_file']]

        self.save()

    def save(self):
        index = {
            'path': self.path,
            'files': self.files,
        }
        with open(self.index_file, 'w') as f:
            json.dump(index, f, indent=4, ensure_ascii=False)

    def load_index(self, allow_rebuild=False):
        if not os.path.exists(self.index_file):
            if allow_rebuild:
                return self.rebuild_index_and_save()

        with open(self.index_file, 'r') as f:
            index = json.load(f)
            self.files = index['files']

    def __getitem__(self, item):
        return self.files[item]

    def find_by_audio_file(self, search):
        for file in self.files:
            if search in file['audio_file']:
                return os.path.join(self.path, file['audio_file'])

    def sort_files(self):
        self.files.sort(key=lambda x: x['audio_file'])
        return self.files

    @staticmethod
    def beautify_title(name: str):
        if name.startswith('lb_') or name.endswith('.mp3'):
            name = name.replace('lb_', '', 1)
            name = name.replace('.mp3', '', 1)
        return name

    @classmethod
    def from_code(cls, code):
        indexer = AudioIndexer(AUDIO_SOURCE_PATH, code)
        try:
            indexer.load_index()
        except FileNotFoundError:
            print("Index file not found.")
        return indexer
