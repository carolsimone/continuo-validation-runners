# continuo-validation-postgres

Postgres adapter for the continuo validation runner. Connection env:
`POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER` (required);
`POSTGRES_PORT` (default 5432), `POSTGRES_PASSWORD` (default empty).
Verification tier: live integration tests against postgres:16.
