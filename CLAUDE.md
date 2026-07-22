# continuo-validation-runners

## Logging vs. stdout

All diagnostic output uses the stdlib `logging` module — never `print`. Every
module that emits diagnostics gets its own logger (`logging.getLogger(__name__)`
or an equivalent stable name); `runner.main()` configures logging once via
`logging.basicConfig(stream=sys.stderr, ...)`. Log records go to stderr, which
continuo's k8s-controller captures as the pod log.

**The one exception**: the runner's sentinel-framed result block
(`result.result_block(...)`, see `core/continuo_validation_core/result.py`) is
wire protocol, not a log line. `runner.py` writes it to stdout with `print(...,
flush=True)` as the process's last stdout line; continuo's k8s-controller parses
it out of the pod log by its `===CONTINUO_VALIDATION_RESULT_BEGIN/END===`
markers.

Consequently: **stdout is reserved exclusively for that one block.**
- Adapters and any other diagnostic code must never write to stdout — use
  `logging` instead, which goes to stderr.
- Adapters must never emit the `===CONTINUO_VALIDATION_RESULT_BEGIN/END===`
  marker strings themselves; only `runner.py` may print a result block.

## Lint, type-check, and tests

- Lint: `uv run ruff check core adapters`
- Type-check (strict): `uv run mypy core/continuo_validation_core adapters/postgres/continuo_validation_postgres`
- Tests are marked with pytest markers `integration` (needs
  `docker-compose.integration.yml` running) and `image` (needs the locally built
  runner image plus the integration stack). Default runs (`-m "not integration and
  not image"`) need neither.
