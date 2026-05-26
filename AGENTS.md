# feeds — RSS Reader

## Rules for agents
- Linting and formatting must be checked and fixed after every code change.
- When planning, always check if documentation (README.md, AGENTS.md, docs/) needs updates and plan accordingly.

## Commands
- `just run` — run the app
- `just build` — build binary (output: dist/main)
- `just format` — run formatting
- `just lint` — run linting

## Conventions
- Python ≥3.10, PySide6, reader lib
- Ruff with all the rules in pyproject.toml
- basedpyright for type checking (lenient config)
- No `__init__.py` re-exports — import from canonical module paths
- @dataclass(frozen=True, slots=True) for data models
- CamelCase for Qt subclasses, snake_case for everything else
- Private methods prefixed `_`
- Use `match`/`case` with `typing.assert_never` for dispatching on enums and sumtypes
- Annotate variable assignments from function calls when the return type is not trivially inferable from the call itself (e.g., `log: Logger = logging.getLogger(...)`, `m: re.Match | None = re.match(...)`)
  Constructor calls (`Foo()`) and well-known stdlib functions (`len()`, `bool()`) need no annotation.
- Always add `logging` to every Python module. Use `log: logging.Logger = logging.getLogger(__name__)`.
  - **INFO** — user actions (button clicks, menu actions), DB inserts/updates/deletes, state-changing operations, action completions.
  - **ERROR** — actions that are aborted (e.g., exceptions that prevent the operation from completing).
  - **WARNING** — recoverable errors (e.g., a network call failed but the operation can continue, a parse error on one of several feeds).

## Docs
- `docs/gui.md` — GUI architecture (FeedsApp, panes, widgets, delegates, dialogs, async threading)
- `docs/rss-atom.md` — RSS/Atom handling (FeedReader, data models, storage, feed updating, read state)
- `docs/discovery.md` — Feed discovery pipeline (platform handlers, HTML autodiscovery, Link headers, path probing)
