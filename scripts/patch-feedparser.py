"""Patch vendored feedparser for Nuitka compatibility.

Removes __code__ assignments (not writable in Nuitka) and replaces
the goahead/parse_starttag overrides with parent-class fallbacks.
"""

import importlib
import logging
import sys
from pathlib import Path

mod = importlib.import_module("reader._vendor.feedparser.html")
path = mod.__file__
if not path or not path.endswith(".py"):
    logging.error("no .py file found: %s", path)
    sys.exit(1)

with Path(path).open() as f:
    src = f.read()

old_block = """    # By declaring these methods and overriding their compiled code
    # with the code from sgmllib, the original code will execute in
    # feedparser's scope instead of sgmllib's. This means that the
    # `tagfind` and `charref` regular expressions will be found as
    # they're declared above, not as they're declared in sgmllib.
    def goahead(self, i):
        raise NotImplementedError

    # Replace goahead with SGMLParser's goahead() code object.
    goahead.__code__ = sgmllib.SGMLParser.goahead.__code__

    def __parse_starttag(self, i):
        raise NotImplementedError

    # Replace __parse_starttag with SGMLParser's parse_starttag() code object.
    __parse_starttag.__code__ = sgmllib.SGMLParser.parse_starttag.__code__

    def parse_starttag(self, i):
        j = self.__parse_starttag(i)
        if self._type == "application/xhtml+xml":
            if j > 2 and self.rawdata[j - 2 : j] == "/>":
                self.unknown_endtag(self.lasttag)
        return j"""

new_block = """    def parse_starttag(self, i):
        j = sgmllib.SGMLParser.parse_starttag(self, i)
        if self._type == "application/xhtml+xml":
            if j > 2 and self.rawdata[j - 2 : j] == "/>":
                self.unknown_endtag(self.lasttag)
        return j"""

src = src.replace(old_block, new_block)

with Path(path).open("w") as f:
    _ = f.write(src)

assert "goahead.__code__" not in src, "patch failed: __code__ still in file"
assert "__parse_starttag.__code__" not in src, (
    "patch failed: __parse_starttag still in file"
)
assert "self.__parse_starttag" not in src, (
    "patch failed: __parse_starttag call still in file"
)
logging.info("patched %s", path)
