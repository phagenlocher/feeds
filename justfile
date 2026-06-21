# List just recipes
list-recipes:
    @just --list


_build-venv:
    uv venv --python 3.11 --seed .build-venv

# Build static binary in dist/
build suffix="": _build-venv
    .build-venv/bin/pip install -q -e . 'nuitka[onefile]==4.1.2'
    # Patch vendored feedparser __code__ assignment for Nuitka compatibility
    .build-venv/bin/python scripts/patch-feedparser.py
    # Patch reader _sqlite_utils dict-comp in finally for Nuitka 4.1 compat
    .build-venv/bin/python scripts/patch-sqlite-utils.py
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

# Print licenses of project dependencies (excluding dev dependencies) with additional arguments for pip-licenses
licenses *args: _build-venv
    uv export --no-dev --no-editable --frozen --no-emit-project -o requirements.txt
    .build-venv/bin/pip install -r requirements.txt
    .build-venv/bin/pip install pip-licenses
    .build-venv/bin/pip-licenses {{args}}
    rm requirements.txt

# Build and install a static binary to ~/.local/bin
install: build
    cp dist/feeds ~/.local/bin/

# Format all files
format:
    uv run ruff format

# Lint all files
lint:
    uv run ruff check

# Run feeds with given arguments
run *args:
    uv run python -m feeds {{args}}
