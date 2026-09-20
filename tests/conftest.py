import os
import tempfile

# core.config reads these at import time; point them to scratch dirs, so tests never touch the real audio DB
os.environ['AUDIO_SOURCE_PATH'] = tempfile.mkdtemp(prefix='sensei_test_db_')
os.environ['BACKUP_PATH'] = tempfile.mkdtemp(prefix='sensei_test_backups_')
