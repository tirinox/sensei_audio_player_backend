import os
import subprocess
from pathlib import Path
from typing import Iterable

from pydub import AudioSegment
from tqdm import tqdm

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


def convert_mp3_to_low_bitrate(file, normalize_volume=True):
    basename = os.path.basename(file)
    base_dir = os.path.dirname(file)

    print(f'Found new file: {basename}')
    basename = normalize_filename(basename)
    basename = f'lb_{basename}'
    print(f'New name: {basename}. Converting to lower bitrate...')
    new_full_name = os.path.join(base_dir, basename)

    # ---------------------------------------------------------
    # 1. LOAD original MP3
    # ---------------------------------------------------------
    sound = AudioSegment.from_file(file, format="mp3")
    orig_db = sound.dBFS

    # ---------------------------------------------------------
    # 2. NORMALIZE to target dBFS
    # ---------------------------------------------------------
    if normalize_volume:
        target_dBFS = -14.0
        sound = normalize_to_target_dbfs(sound, target_dBFS)
        norm_db = sound.dBFS
        print(f"Volume: {orig_db:.1f} dBFS → {norm_db:.1f} dBFS (target {target_dBFS})")

    # ---------------------------------------------------------
    # 3. EXPORT temporary WAV (better quality for re-encode)
    # ---------------------------------------------------------
    tmp_wav = Path(base_dir) / (basename + ".tmp.wav")
    sound.export(tmp_wav, format="wav")

    # ---------------------------------------------------------
    # 4. FINAL ENCODE to low-bitrate MP3
    # ---------------------------------------------------------
    os.system(f'ffmpeg -y -i "{tmp_wav}" -b:a 128k "{new_full_name}"')

    # remove temporary WAV
    os.remove(tmp_wav)

    # ---------------------------------------------------------
    # 5. Print size
    # ---------------------------------------------------------
    new_size = os.path.getsize(new_full_name)
    print(f'New size: {new_size / (1024 * 1024):.2f} MB')

    return new_full_name


def is_processed_mp3_lb(file):
    basename = os.path.basename(file)
    return basename.startswith('lb')


def normalize_to_target_dbfs(sound: AudioSegment, target_dBFS: float = -16.0) -> AudioSegment:
    """
    Normalize an AudioSegment to a target dBFS.
    Typical music streaming target is around -14 LUFS,
    but here we’re using dBFS as a simple approximation.
    """
    change_in_dBFS = target_dBFS - sound.dBFS
    return sound.apply_gain(change_in_dBFS)


def get_mp3_bitrate(path: Path) -> str:
    """
    Returns bitrate like '128k', '64k', '320k'
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=bit_rate",
        "-of", "default=nw=1:nk=1",
        str(path)
    ]
    out = subprocess.check_output(cmd).decode().strip()
    bitrate = int(out) // 1000  # to k
    return f"{bitrate}k"


def normalize_mp3_batch(files: Iterable[str | Path], target_dBFS: float = -16.0):
    """
    Normalizes MP3 loudness while preserving original bitrate.
    """
    for f in tqdm(list(files), desc="Normalizing MP3s"):
        path = Path(f)
        if not path.is_file():
            print(f"Skipping (not a file): {path}")
            continue

        try:
            # Read bitrate first
            bitrate = get_mp3_bitrate(path)

            # Load original
            sound = AudioSegment.from_file(path, format="mp3")
            orig_db = sound.dBFS

            # Normalize
            normalized = normalize_to_target_dbfs(sound, target_dBFS=target_dBFS)
            norm_db = normalized.dBFS

            # Export with the same bitrate
            normalized.export(path, format="mp3", bitrate=bitrate)

            print(f"{path.name}: {orig_db:.1f} dBFS → {norm_db:.1f} dBFS (bitrate kept {bitrate})")

        except Exception as e:
            print(f"Error processing {path}: {e}")
