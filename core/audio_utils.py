import json
import math
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Iterable

from pydub import AudioSegment
from tqdm import tqdm

from core.config import NORMALIZE_TO_DBFS
from core.file_man import normalize_filename


def load_audio_file(file_path):
    try:
        return AudioSegment.from_mp3(file_path)
    except Exception as e:
        print(f"Failed to load audio file: {e}")
        raise


def mp3_length_seconds(path: str) -> float:
    cmd = f'ffprobe -v error -select_streams a:0 ' \
          f'-show_entries stream=duration -of json {shlex.quote(str(path))}'
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
    return float(json.loads(out.stdout)['streams'][0]['duration'])


def get_peak_dbfs(sound: AudioSegment) -> float:
    """
    Return peak level in dBFS.
    0 dBFS = full scale, values are <= 0.
    """
    peak_sample = sound.max  # integer sample amplitude
    if peak_sample == 0:
        return float("-inf")  # silence

    max_possible = float(2 ** (8 * sound.sample_width - 1))
    peak_dbfs = 20 * math.log10(peak_sample / max_possible)
    return peak_dbfs


def convert_mp3_to_low_bitrate(file, normalize_volume=True, target_dbfs=NORMALIZE_TO_DBFS):
    old_basename = os.path.basename(file)
    base_dir = os.path.dirname(file)

    print(f'Found new file: {old_basename}')
    new_basename = normalize_filename(old_basename)
    new_basename = f'lb_{new_basename}'
    print(f'New name: {new_basename}. Converting to lower bitrate...')
    new_full_name = os.path.join(base_dir, new_basename)

    # ---------------------------------------------------------
    # 1. LOAD original MP3
    # ---------------------------------------------------------
    sound = AudioSegment.from_file(file, format="mp3")
    orig_db = sound.dBFS

    # ---------------------------------------------------------
    # 2. NORMALIZE to target dBFS
    # ---------------------------------------------------------
    if normalize_volume:
        sound, debug = normalize_safely(sound, target_dBFS=target_dbfs)
        norm_db = sound.dBFS
        print(f"Volume: {orig_db:.1f} dBFS → {norm_db:.1f} dBFS (target {target_dbfs})")

    # ---------------------------------------------------------
    # 3. EXPORT temporary WAV (better quality for re-encode)
    # ---------------------------------------------------------
    tmp_wav = Path(base_dir) / (new_basename + ".tmp.wav")
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


def normalize_to_target_dbfs(sound: AudioSegment, target_dbfs: float = NORMALIZE_TO_DBFS) -> AudioSegment:
    change_in_dBFS = target_dbfs - sound.dBFS
    return sound.apply_gain(change_in_dBFS)


def normalize_safely(
        sound: AudioSegment,
        target_dBFS: float = NORMALIZE_TO_DBFS,
        peak_margin_db: float = 1.0,
):
    """
    Try to normalize to target_dBFS, but never let peak go above -peak_margin_db.
    Returns (normalized_sound, debug_info_dict).
    """
    rms_db = sound.dBFS
    peak_db = get_peak_dbfs(sound)

    # Gain needed to hit target RMS
    desired_gain = target_dBFS - rms_db

    # Max gain allowed so that peak <= -peak_margin_db
    # e.g. peak_margin_db=1.0 -> max peak at -1 dBFS
    max_peak_allowed = -peak_margin_db
    max_gain = max_peak_allowed - peak_db

    # Actual gain we can safely apply
    applied_gain = min(desired_gain, max_gain)

    normalized = sound.apply_gain(applied_gain)

    debug = {
        "rms_db_before": rms_db,
        "peak_db_before": peak_db,
        "desired_gain_db": desired_gain,
        "max_gain_db_no_clip": max_gain,
        "applied_gain_db": applied_gain,
        "rms_db_after": normalized.dBFS,
        "peak_db_after": get_peak_dbfs(normalized),
    }
    return normalized, debug


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


def normalize_mp3_batch(files: Iterable[str | Path], target_dbfs: float = NORMALIZE_TO_DBFS):
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
            # normalized = normalize_to_target_dbfs(sound, target_dbfs=target_dbfs)

            normalized, debug = normalize_safely(sound, target_dBFS=target_dbfs)
            print(debug)

            norm_db = normalized.dBFS

            # Export with the same bitrate
            normalized.export(path, format="mp3", bitrate=bitrate)

            print(f"{path.name}: {orig_db:.1f} dBFS → {norm_db:.1f} dBFS (bitrate kept {bitrate})")

        except Exception as e:
            print(f"Error processing {path}: {e}")


def au_sep(delay=0.1):
    print('---' * 40)
    time.sleep(delay)
    os.system("afplay /System/Library/Sounds/Ping.aiff")
    time.sleep(delay)
