"""Patch reader._storage._sqlite_utils for Nuitka 4.1.x compatibility.

Replaces a dict comprehension inside a finally block with a plain for-loop
to avoid a Nuitka crash in the try/finally clone logic.
"""

import importlib
import logging
import sys
from pathlib import Path

mod = importlib.import_module("reader._storage._sqlite_utils")
path = mod.__file__
if not path or not path.endswith(".py"):
    logging.error("no .py file found: %s", path)
    sys.exit(1)

with Path(path).open() as f:
    src = f.read()

old_block = """                data['io_counters'] = {
                    f: getattr(end_io_counters, f) - getattr(start_io_counters, f)
                    for f in fields
                }"""

new_block = (
    """                data['io_counters'] = {}
                for f in fields:
                    data['io_counters'][f] = """
    """getattr(end_io_counters, f) - getattr(start_io_counters, f)"""
)

if old_block not in src:
    logging.error("patch target not found in %s", path)
    sys.exit(1)

src = src.replace(old_block, new_block)

with Path(path).open("w") as f:
    _ = f.write(src)

assert old_block not in src, "patch failed: dict comprehension still in file"
logging.info("patched %s", path)
