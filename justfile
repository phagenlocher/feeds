_static-venv:
    rm -rf .static-venv
    uv venv --python 3.11 --seed .static-venv
    .static-venv/bin/pip install -q -e . 'nuitka[onefile]==4.1.2'
    # Patch vendored feedparser __code__ assignment for Nuitka compatibility
    .static-venv/bin/python3 scripts/patch-feedparser.py
    # Patch reader _sqlite_utils dict-comp in finally for Nuitka 4.1 compat
    .static-venv/bin/python3 scripts/patch-sqlite-utils.py

build: _static-venv
    .static-venv/bin/nuitka \
      --onefile \
      --enable-plugin=pyside6 \
      --include-package=reader \
      --noinclude-pytest-mode=nofollow \
      --output-filename=feeds \
      --output-dir=dist \
      --deployment \
      --python-flag=-m \
      feeds
    rm -rf dist/*.build dist/*.dist dist/*.onefile-build

install: build
    cp dist/feeds ~/.local/bin/

format:
    uv run ruff format

lint:
    uv run ruff check

run *args:
    uv run python -m feeds {{args}}
