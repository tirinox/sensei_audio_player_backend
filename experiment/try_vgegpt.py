import os

from dotenv import load_dotenv

from core.config import AUDIO_SOURCE_PATH
from core.furigana_neural import FugiranaNeural
from core.indexer import AudioIndexer
from core.segment_man import SegmentManager

load_dotenv()


def main():
    os.chdir("..")

    f = FugiranaNeural()

    # print(f.generate_furigana(["私は猫です", "私は犬です"]))
    indexer = AudioIndexer(f"{AUDIO_SOURCE_PATH}")
    try:
        indexer.load_index()
    except FileNotFoundError:
        print("Index file not found.")

    example = indexer.find_by_audio_file("23-B1")
    seg = SegmentManager(example)
    seg.load()

    sentences = [s["text"] for s in seg.sorted_segments]

    furiganed_sentences = f.generate_furigana(sentences)

    seg.update_texts(furiganed_sentences)
    seg.save(save_as="furigana_test")


if __name__ == '__main__':
    main()
