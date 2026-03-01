import os.path
import sys

import tqdm
from dotenv import load_dotenv

from core.audio_utils import normalize_mp3_batch, convert_mp3_to_low_bitrate, load_audio_file, mp3_length_seconds, \
    au_sep
from core.config import AUDIO_SOURCE_PATH
from core.file_man import waveform_out_path, ask_to_choose_the_code, is_processed_mp3_lb
from core.furigana_neural import FuriganaNeural
from core.indexer import AudioIndexer
from core.player import Player
from core.process_segments import fill_text_for
from core.segment_man import SegmentManager
from core.splitter import split_file
from core.tui import run_menu
from core.waveform import audio_to_waveform_png

load_dotenv()


def play_demo_segments():
    example = get_example()
    print("Processing example:", example)

    player = Player(example)

    while True:
        player.play_current_segment()
        au_sep()
        player.shift(1)


def get_example():
    code = ask_to_choose_the_code()
    indexer = AudioIndexer.from_code(code)

    try:
        example = sys.argv[2].strip()
        if example.isdigit():
            print("Example is a number. Trying to find file by index.")
            example = int(example)
            files = indexer.get_all_mp3()
            example = files[example - 1]
            print(f'You picked: {example}')
            if input('Are you sure? (y/n) ').strip().lower() != 'y':
                print("Aborting.")
                sys.exit(0)
        if os.path.dirname(example) == '':
            print("Example is a filename. Trying to find it in the database path.")
            example = os.path.join(AUDIO_SOURCE_PATH, example)
    except IndexError:
        files = indexer.get_all_mp3()
        example_index = run_menu(files, timeout=0)
        example = files[example_index]

    return example


def force_speech_recognition(example, skip_existing_text=True, force_split=False):
    if not example:
        raise ValueError("Example file path is required.")

    print(f"Running speech recognition for: {example}...")

    audio_file = load_audio_file(example)
    metadata = SegmentManager(example)

    if force_split or not metadata.load():
        split_file(audio_file, metadata)
        metadata.save()

    fill_text_for(metadata, audio=audio_file, skip_existing=skip_existing_text)


def have_fun_waveform(query='ここはどこですか'):
    code = ask_to_choose_the_code()
    indexer = AudioIndexer.from_code(code)
    example = indexer.find_by_audio_file(query)
    if not example:
        print("Example not found.")
        return

    player = Player(example)
    index = 5
    _, _, piece = player[index]

    # audio_to_waveform_png(piece)
    # player.play_segment(5)

    audio_to_waveform_png(player.audio, output_path=waveform_out_path(example, index))


def normalize_all_volumes():
    code = ask_to_choose_the_code()
    indexer = AudioIndexer.from_code(code)
    all_files = indexer.get_all_mp3()
    normalize_mp3_batch(all_files)


def reindex(code=None):
    code = code or ask_to_choose_the_code()
    indexer = AudioIndexer.from_code(code)
    indexer.rebuild_index_and_save()
    indexer.sort_files()
    indexer.save()


def furiganate_all(indexer):
    furiganator = FuriganaNeural.from_env()
    all_files = indexer.get_all_mp3()

    # processing
    for file in tqdm.tqdm(all_files):
        seg = SegmentManager(file)
        seg.load()

        if seg.all_has_original_text:
            print(f"Skipping {file} as it already has original text. Likely already furiganated.")
            continue

        sentences = seg.original_sentences
        furiganed_sentences = furiganator.generate_furigana(sentences)

        seg.update_texts(furiganed_sentences)
        seg.save()


def process_incoming(only_new=True):
    code = ask_to_choose_the_code()
    indexer = AudioIndexer.from_code(code)
    all_files = indexer.get_all_mp3()

    new_files = []

    # renaming and converting
    for file in tqdm.tqdm(all_files):
        if not is_processed_mp3_lb(file):
            # new file detected, convert and rename
            new_full_name = convert_mp3_to_low_bitrate(file, normalize_volume=True)

            new_files.append(new_full_name)

            # remove the original file
            os.remove(file)

    reindex(code)

    # load again
    all_files = indexer.get_all_mp3()

    # processing
    realm = new_files if only_new else all_files
    for file in tqdm.tqdm(realm):
        force_speech_recognition(file, skip_existing_text=True)

    reindex(code)

    furiganate_all(indexer)


def list_files():
    code = ask_to_choose_the_code()
    indexer = AudioIndexer.from_code(code)
    files = indexer.get_all_mp3()
    for i, file in enumerate(files):
        print(f'{i + 1}. {os.path.basename(file)}')


def foo_func():
    code = ask_to_choose_the_code()

    indexer = AudioIndexer.from_code(code)
    all_files = indexer.get_all_mp3()

    example_index = run_menu(all_files, timeout=0)
    example = all_files[example_index]
    print(example)

    seconds = mp3_length_seconds(example)
    print(f"Length of {example}: {seconds} seconds")

    normalize_mp3_batch([
        example
    ])


def convert_ruby():
    example = get_example()
    print("Converting Ruby for example:", example)
    metadata = SegmentManager(example)
    metadata.load()
    metadata.convert_ruby_to_parenthesis()
    print("Converted to parenthesis")
    input("Press Enter to continue...")
    metadata.save()


def cvt_seg_from_dict_to_arr():
    code = ask_to_choose_the_code()
    indexer = AudioIndexer.from_code(code)
    all_files = indexer.get_all_mp3()

    for file in tqdm.tqdm(all_files):
        metadata = SegmentManager(file)
        if not metadata.load():
            print(f"Error loading metadata for {file}")
            continue
        metadata.save()


def furigana_1():
    code = ask_to_choose_the_code()

    indexer = AudioIndexer.from_code(code)
    all_files = indexer.get_all_mp3()

    example_index = run_menu(all_files, timeout=0)
    example = all_files[example_index]

    seg = SegmentManager(example)
    seg.load()

    sentences = seg.original_sentences

    furiganator = FuriganaNeural.from_env()
    furiganed_sentences = furiganator.generate_furigana(sentences)

    seg.update_texts(furiganed_sentences)
    seg.save()


def update_one_file():
    example = get_example()

    force_speech_recognition(example, skip_existing_text=False, force_split=True)

    furiganator = FuriganaNeural.from_env()

    seg = SegmentManager(example)
    seg.load()

    sentences = seg.original_sentences
    furiganed_sentences = furiganator.generate_furigana(sentences)

    seg.update_texts(furiganed_sentences)
    seg.save()


command_map = {
    'reindex': reindex,
    'waveform': have_fun_waveform,
    'update': update_one_file,
    'play_demo': play_demo_segments,
    'process_incoming': process_incoming,
    'list': list_files,
    'foo': foo_func,
    'convert_ruby': convert_ruby,
    'cvt_seg_v3': cvt_seg_from_dict_to_arr,
    'furiganate': furigana_1,
    'normalize_volumes': normalize_all_volumes,
}

if __name__ == '__main__':
    command = sys.argv[1] if len(sys.argv) > 1 else None
    if not command:
        print("No command provided. Available commands: ", list(command_map.keys()))
        sys.exit(1)

    print(f'{AUDIO_SOURCE_PATH = }')

    command = command.strip().lower()
    if command in command_map:
        print("Running command:", command)
        command_map[command]()
    else:
        print("Unknown command. Available commands: ", list(command_map.keys()))
