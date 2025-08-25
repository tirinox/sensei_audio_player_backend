import os

from .config import AUDIO_SOURCE_PATH
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


def convert_mp3_to_low_bitrate(file):
    basename = os.path.basename(file)
    base_dir = os.path.dirname(file)

    print(f'Found new file: {basename}')
    basename = basename.replace('-kissvk.com', '')
    basename = basename.replace('My Recording-', '')
    basename = basename.replace('My Recording - ', '')
    basename = basename.replace('Неизвестный-', '')
    basename = basename.replace(' [audiovk.com]', '')
    basename = f'lb_{basename}'
    print(f'New name: {basename}. Converting to lower bitrate...')
    new_full_name = os.path.join(base_dir, basename)
    os.system(f'ffmpeg -i "{file}" -b:a 128k "{new_full_name}"')

    # print size in mb
    new_size = os.path.getsize(new_full_name)
    new_size_mb = new_size / (1024 * 1024)
    print(f'New size of {new_full_name}: {new_size_mb:.2f} MB')

    return new_full_name


def is_processed_mp3_lb(file):
    basename = os.path.basename(file)
    return basename.startswith('lb')
