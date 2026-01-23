import os

from dotenv import load_dotenv

load_dotenv()

AUDIO_SOURCE_PATH = os.path.abspath(os.environ.get('AUDIO_SOURCE_PATH'))

NORMALIZE_TO_DBFS = -19.0
