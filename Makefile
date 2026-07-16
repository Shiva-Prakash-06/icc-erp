.PHONY: install test lint db-upgrade demo-import run

install:
	python -m pip install -r requirements.txt

test:
	python -m unittest discover -s tests -p '*test.py' -v

db-upgrade:
	flask --app run:app db upgrade

run:
	flask --app run:app run --debug

demo-import:
	flask --app run:app demo-import-supplied
