import os
import subprocess
from pathlib import Path
from typing import Iterable

from pydub import AudioSegment
from tqdm import tqdm

from .config import AUDIO_SOURCE_PATH, NORMALIZE_TO_DBFS
from .tui import run_menu


def get_all_mp3(path):
    """
    Get all mp3 files in the specified directory.
    :param path:
    :return:
    """
    mp3_files = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".mp3"):
                mp3_files.append(os.path.join(root, file))
    mp3_files.sort(reverse=True)
    return mp3_files


def waveform_out_path(original_file_name, index):
    base_name = os.path.basename(original_file_name)
    base_path = os.path.dirname(original_file_name)
    os.makedirs(os.path.join(base_path, 'waveforms', base_name), exist_ok=True)
    return os.path.join(base_path, 'waveforms', base_name, f'wf_{index:03}.png')


def get_all_codes(basepath):
    """
    Return all subdirectories in the specified directory, if its name starts with JP
    :param basepath:
    :return:
    """
    return [f for f in os.listdir(basepath) if os.path.isdir(os.path.join(basepath, f)) and f.startswith('JP')]


def ask_to_choose_the_code():
    codes = get_all_codes(AUDIO_SOURCE_PATH)
    if not codes:
        print("No codes found.")
        exit(1)

    code = os.environ.get('CODE', '').strip().upper()
    if code not in codes:
        print("No code specified in the environment. Choose one from the list.")
    else:
        print(f"Using code from the environment: {code}")
        return code

    index_selected = run_menu(codes, 5, codes.index("JPLTX"))
    return codes[index_selected]


def normalize_filename(basename):
    for pat in [
        '-kissvk.com',
        'My Recording-',
        'My Recording - ',
        'Неизвестный-',
        ' [audiovk.com]',
    ]:
        basename = basename.replace(pat, '')
    return basename



def is_processed_mp3_lb(file):
    basename = os.path.basename(file)
    return basename.startswith('lb')

