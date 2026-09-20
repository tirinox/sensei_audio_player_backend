import os
import tempfile

# core.config reads this at import time; point it to a scratch dir, so tests never touch the real audio DB
os.environ['AUDIO_SOURCE_PATH'] = tempfile.mkdtemp(prefix='sensei_test_db_')
