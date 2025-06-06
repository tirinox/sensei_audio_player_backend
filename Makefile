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

.PHONY: remake
remake: # Rescan the audio file using specified pause duration
	python pg.py remake

.PHONY: foo
foo: # Placeholder for future tasks.
	python pg.py foo
