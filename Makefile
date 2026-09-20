default: help

.PHONY: help
help: # Show help for each of the Makefile recipes.
	@grep -E '^[a-zA-Z0-9 -]+:.*#'  Makefile | sort | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#')\n"; done

.PHONY: reindex
reindex: # Reindex the database.
	python pg.py reindex

.PHONY: list
list: # List all the tables in the database.
	python pg.py list

.PHONY: process-incoming
process-incoming: # Process incoming messages.
	python pg.py process_incoming

.PHONY: upload
upload: # Upload the audio files.
	scripts/upload.sh

.PHONY: upload-dry
upload-dry: # Show what upload would copy and delete on the host, without doing it.
	scripts/upload.sh --dry-run

.PHONY: update
update: # Rescan the audio file using specified pause duration
	python pg.py update

.PHONY: furiganate
furiganate: # Furiganate the database entries.
	python pg.py furiganate

.PHONY: foo
foo: # Placeholder for future tasks.
	python pg.py foo

.PHONY: editor
editor: # Run the web editor (segments, pipeline steps) at http://127.0.0.1:8377
	python -m uvicorn editor.server:app --host 127.0.0.1 --port 8377 --timeout-graceful-shutdown 2

.PHONY: webui
webui: editor # Same as editor (the old name).
