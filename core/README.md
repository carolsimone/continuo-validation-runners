# continuo-validation-core

Engine-agnostic core of the continuo blue/green validation runner: op dispatch,
structured result-block contract, candidate-SQL fetch from S3, and the
`WarehouseAdapter` port. Engine support is provided by separately installed
`continuo-validation-<engine>` packages registering a
`continuo_validation.adapters` entry point; each runner image installs core plus
exactly one adapter.
