# feeds — RSS Reader

## Commands
- `just run` — run the app
- `just build` — build PyInstaller binary (output: dist/main)
- `just format` — ruff format feeds/
- `just lint` — run basedpyright
- `uv run ruff check feeds/` — ruff lint

## Conventions
- Python ≥3.10, PySide6, reader lib
- Ruff with all the rules in pyproject.toml (D, N802 ignored in feeds/)
- basedpyright for type checking (lenient config)
- No `__init__.py` re-exports — import from canonical module paths
- @dataclass(frozen=True, slots=True) for data models
- CamelCase for Qt subclasses, snake_case for everything else
- Private methods prefixed `_`
- Use `match`/`case` with `typing.assert_never` for dispatching on enums and sumtypes
- Annotate variable assignments from function calls when the return type is not trivially inferable from the call itself (e.g., `log: Logger = logging.getLogger(...)`, `m: re.Match | None = re.match(...)`)
  Constructor calls (`Foo()`) and well-known stdlib functions (`len()`, `bool()`) need no annotation.
