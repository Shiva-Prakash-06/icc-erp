.PHONY: install test lint db-upgrade demo-import start run

install:
	python -m pip install -r requirements.txt

test:
	python -m unittest discover -s tests -p '*test.py' -v

db-upgrade:
	flask --app run:app db upgrade

start:
	bash scripts/start.sh

run: start

demo-import:
	flask --app run:app demo-import-supplied
