# continuo-validation-runners

A library-only monorepo: each top-level folder (e.g. `postgres/`) is a PyPI
library implementing `continuo_validation_contract.port.WarehouseAdapter`. No
Dockerfiles or runner images live in this repo — continuo's `validation-runner`
harness (in the `continuo` repo) installs one engine library into a slim image
at build time.

## Logging vs. stdout

All diagnostic output uses the stdlib `logging` module — never `print`. Every
module that emits diagnostics gets its own logger (`logging.getLogger(__name__)`
or an equivalent stable name).

**The wire contract**: continuo's harness prints a sentinel-framed result block
(`continuo_validation_contract.result.result_block(...)`) to stdout as the
process's last stdout line; continuo's k8s-controller parses it out of the pod
log by its `===CONTINUO_VALIDATION_RESULT_BEGIN/END===` markers. Consequently:
**stdout is reserved exclusively for that one block, printed by the harness.**
- Adapters and any other diagnostic code in this repo must never write to
  stdout — use `logging` instead, which goes to stderr.
- Adapters must never emit the `===CONTINUO_VALIDATION_RESULT_BEGIN/END===`
  marker strings themselves; only continuo's harness may print a result block.

## Lint, type-check, and tests

- Lint (per library): `uv run ruff check <lib>`, e.g. `uv run ruff check postgres`,
  `uv run ruff check trino`
- Type-check (strict, per library): `uv run mypy <lib>/continuo_validation_<lib>`,
  e.g. `uv run mypy postgres/continuo_validation_postgres`
- Tests are marked with the pytest marker `integration` (needs
  `docker-compose.integration.yml` running). Default runs (`-m "not
  integration"`) need it not running.
- Adapter DDL behavior (schema creation, table builds, clones) is verified
  against live engines in the `integration`-marked tests, not mocked
  connections/cursors. Do not add mock-DB unit tests for DDL behavior.

## Dependency on the contract

`continuo_validation_contract` (the `WarehouseAdapter` port + result-block wire
format) is a separate published package, pinned exactly (e.g.
`continuo-validation-contract==0.1.0`) in each library's `pyproject.toml`. Until it
is on real PyPI it resolves from a **package-scoped** TestPyPI index declared in the
root `pyproject.toml` (`[[tool.uv.index]]` + `[tool.uv.sources]`). Never export a
global `UV_EXTRA_INDEX_URL` — a blanket TestPyPI index makes uv pull the sdist-only
TestPyPI `psycopg2-binary`, which fails to compile on clean systems.
