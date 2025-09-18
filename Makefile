PY=python
PIP=pip

.PHONY: fmt lint type test all

fmt:
	ruff format .

lint:
	ruff check .

type:
	mypy .

test:
	pytest -q

all: fmt lint type test
