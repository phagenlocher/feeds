# Nuitka Patches

feeds must patch two third-party dependencies to work around Nuitka
limitations. Both patches are applied in `justfile`'s `_static-venv` recipe
before the build runs.

---

## 1. feedparser `__code__` assignment

**File:** `scripts/patch-feedparser.py`
**Target:** `reader._vendor.feedparser.html`

feedparser's vendored HTML parser uses a CPython-internal trick: it
defines stub methods (`goahead`, `__parse_starttag`) then overwrites
their `__code__` attribute with the compiled code from
`sgmllib.SGMLParser`. This lets the methods execute in feedparser's
scope so its regex patterns resolve correctly.

Nuitka does not support `__code__` assignment — compiled code objects
are not writable in Nuitka's compiled environment. Attempting to build
unpatched produces:

```
RuntimeError: __code__ is not writable
```

The patch removes the `__code__` swap entirely and replaces the
`parse_starttag` override with a plain parent-class call via
`sgmllib.SGMLParser.parse_starttag(self, i)`, keeping only the XHTML
self-closing-tag logic that was specific to the override.

---

## 2. reader `_sqlite_utils` dict comprehension in `finally`

**File:** `scripts/patch-sqlite-utils.py`
**Target:** `reader._storage._sqlite_utils`

The reader library's debug-logging wrapper around sqlite3 contains a
dict comprehension inside a `try`/`finally` block:

```python
data['io_counters'] = {
    f: getattr(end_io_counters, f) - getattr(start_io_counters, f)
    for f in fields
}
```

Nuitka 4.1.x has a bug in its AST clone logic for `try`/`finally`: when
it clones the `finally` body, a temporary variable
(`dictcontraction_1__.0_clone`) created for the dict comprehension
collides with one already registered, producing:

```
AssertionError: dictcontraction_1__.0_clone
```

This is a Nuitka compiler bug, not a problem with the Python code
itself. The patch converts the dict comprehension into an equivalent
plain `for` loop that produces the same result without triggering the
bug.

This code path is only exercised when debug logging is enabled
(`# pragma: no cover`), so the patch has no effect on release builds.
