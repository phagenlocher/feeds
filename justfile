_build-venv:
    uv venv --python 3.11 --seed .build-venv
    .build-venv/bin/pip install -q -e . 'nuitka[onefile]==4.1.2'
    # Patch vendored feedparser __code__ assignment for Nuitka compatibility
    .build-venv/bin/python scripts/patch-feedparser.py
    # Patch reader _sqlite_utils dict-comp in finally for Nuitka 4.1 compat
    .build-venv/bin/python scripts/patch-sqlite-utils.py

build suffix="": _build-venv
    .build-venv/bin/nuitka \
      --onefile \
      --enable-plugin=pyside6 \
      --include-package=reader \
      --noinclude-pytest-mode=nofollow \
      --output-filename=feeds{{suffix}} \
      --output-dir=dist \
      --deployment \
      --python-flag=-m \
      --lto=yes \
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
