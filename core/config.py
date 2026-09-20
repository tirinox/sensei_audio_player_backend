import os

from dotenv import load_dotenv

load_dotenv()

AUDIO_SOURCE_PATH = os.path.abspath(os.environ.get('AUDIO_SOURCE_PATH'))

NORMALIZE_TO_DBFS = -19.0

# previous versions of segment files are kept here by the editor; outside of the audio DB, so it is never uploaded
BACKUP_PATH = os.path.abspath(os.environ.get('BACKUP_PATH') or
                              os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backups'))
