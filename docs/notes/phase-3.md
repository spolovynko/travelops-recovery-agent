# Phase 3 notes — PostgreSQL persistence and service boundaries

## What this phase shipped

Phase 3 added:

- A PostgreSQL 18 development service exposed only on `127.0.0.1:55432`
- Direct, locked SQLAlchemy, Psycopg, and Alembic dependencies
- Separate SQLAlchemy records for all Phase 2 business entities and associations
- Explicit keys, foreign keys, checks, uniqueness, nullability, indexes, and
  timezone-aware timestamps
- One reviewed Alembic revision that builds the schema from an empty database
- Explicit mapping in both directions between records and domain objects
- A domain-oriented repository interface and SQLAlchemy implementation
- An application service and unit of work that define atomic transactions
- Controlled seed, replace, reset, count, and complete-case retrieval commands
- Unit tests plus isolated integration tests against real PostgreSQL

The main database workflow is:

```powershell
uv run --locked alembic upgrade head
uv run --locked python -m travelops_recovery_agent.persistence.cli seed --seed 42
uv run --locked python -m travelops_recovery_agent.persistence.cli counts
uv run --locked python -m travelops_recovery_agent.persistence.cli show-case CASE-0007
```

## How it works

```text
Database CLI
    → RecoveryDataService
    → SQLAlchemyRecoveryDataUnitOfWork
    → SQLAlchemyRecoveryDataRepository
    → explicit domain/record mapping
    → SQLAlchemy session and PostgreSQL transaction
    → migrated PostgreSQL tables
```

[`application/services.py`](../../src/travelops_recovery_agent/application/services.py)
owns workflows such as safe seeding and reset. It depends on application-owned
protocols, not SQLAlchemy. [`persistence/unit_of_work.py`](../../src/travelops_recovery_agent/persistence/unit_of_work.py)
opens the concrete session and commits or rolls it back. The repository in
[`persistence/repositories.py`](../../src/travelops_recovery_agent/persistence/repositories.py)
performs domain-oriented storage operations without deciding when to commit.

[`persistence/models.py`](../../src/travelops_recovery_agent/persistence/models.py)
describes storage. [`persistence/mapping.py`](../../src/travelops_recovery_agent/persistence/mapping.py)
converts records to and from the independent Phase 2 domain. Alembic, rather
than application startup, applies the schema in [`migrations/`](../../migrations/).

## Concepts I can explain

### Domain model, persistence model, and API schema

A domain model describes airline meaning and invariants. A persistence model
describes how facts occupy tables and relate through keys. An API schema
describes what crosses an HTTP boundary. They may represent similar facts, but
changing a database index should not change an HTTP response or the definition
of a valid itinerary. Phase 3 therefore did not add SQLAlchemy to the Pydantic
domain and did not reuse FastAPI schemas as database records.

### ORM, table, row, column, and mapper

A table is a named collection of rows. A row is one stored record, and a column
is one typed field shared by every row in that table. An object-relational
mapper, or ORM, translates between Python objects and relational rows.
SQLAlchemy's declarative models define mapped Python classes whose columns and
relationships also provide metadata to Alembic. The ORM reduces repetitive SQL;
it does not remove the need to design a relational schema deliberately.

### Keys, constraints, nullability, and indexes

A primary key uniquely identifies a row. Phase 2 stable identifiers remain the
database primary keys. A foreign key requires a referenced row to exist. A
unique constraint prevents repeated combinations, such as a segment sequence
within one booking. A check constraint enforces a row-level rule, such as a
positive rebooking window. Nullability states whether a value may be absent.
An index is an additional lookup structure that makes selected reads faster at
the cost of storage and extra work on writes. Foreign-key and case lookup paths
receive explicit indexes where PostgreSQL does not create them automatically.

### One-to-many, many-to-many, and association tables

One booking has many itinerary segments, so the segment table stores a booking
foreign key. Bookings and passengers are many-to-many: a booking can contain
several passengers and a passenger could appear in several bookings. The
`booking_passengers` association table stores one unique pair of IDs. It is a
real relational table, not an array hidden inside the booking row.

### Normalization, JSON documents, and disruption details

Normalization stores distinct concepts once and connects them with keys. It
allows PostgreSQL to reject missing passengers, duplicated relationships, and
incoherent segment references. Storing the complete dataset as one JSON
document would hide those guarantees and make ordinary relational queries
harder. JSONB is reasonable for genuinely flexible, auxiliary data whose shape
changes independently and does not require strong relational constraints.
Here, the three disruption variants are known and important, so typed nullable
columns plus check constraints make their rules visible and enforceable.

### Session, connection, transaction, commit, rollback, and atomicity

An engine owns connection configuration and a pool of reusable database
connections. A session is SQLAlchemy's working context for loaded and pending
objects; it borrows a connection when needed. A transaction groups statements.
Commit makes all successful changes durable. Rollback discards the transaction.
Atomicity means a multi-record seed is all-or-nothing, so an interruption cannot
leave half a dataset behind.

SQLAlchemy's identity map ensures that one session normally represents one
database identity with one Python record object. It helps keep related changes
consistent, but sessions should remain short-lived and must not be shared as
global state.

### Repository, dependency inversion, application service, and unit of work

The repository exposes operations in application language: add a validated
dataset, count managed records, clear them, or retrieve a complete recovery
case. It does not expose arbitrary SQL. The application owns the repository and
unit-of-work protocols; persistence supplies SQLAlchemy implementations. This
is dependency inversion: higher-level workflows define what they require,
while the database adapter depends on those requirements.

The application service decides the transaction-sized workflow. The unit of
work supplies one repository within one session and commits on success or rolls
back on failure. The repository performs storage operations but never commits
on its own. Future Phase 4 tools can call the application service without
learning SQLAlchemy or controlling transactions.

### Explicit mapping and corrupted stored data

Mapping is the translation between validated domain objects and persistence
records. Writing uses domain-to-record functions. Reading reconstructs domain
models through normal Pydantic validation. If stored data violates a domain
invariant, the mapping boundary raises `PersistenceMappingError` with the
entity identity instead of silently returning an invalid business object.

### Migration versus `create_all()`

`metadata.create_all()` creates whichever tables the current code happens to
describe, but it does not provide a reviewed history for evolving an existing
database. An Alembic revision is one versioned schema change. `upgrade` applies
changes, `downgrade` reverses them when supported, and the `alembic_version`
table records migration history. Production schema changes must be explicit so
they can be reviewed, ordered, tested from zero, and coordinated with running
code. Application import and startup therefore never create tables.

### Database URLs, secrets, and connection pooling

The database URL identifies the driver, user, host, port, and database. It is
loaded from `TRAVELOPS_DATABASE_URL` as a secret setting and is absent from
source code, migrations, and normal CLI errors. Passwords with special
characters are URL-encoded. SQLAlchemy's engine keeps a small pool rather than
opening a brand-new network connection for every operation, and
`pool_pre_ping=True` detects a dead pooled connection before using it.

### Synchronous versus asynchronous SQLAlchemy

Phase 3 uses synchronous SQLAlchemy and Psycopg. The workflows are small CLI and
service operations, so synchronous control flow makes sessions, exceptions,
and transaction boundaries easier to learn. Async database access can help a
high-concurrency service avoid blocking worker capacity, but it would add a
second concurrency model before the project has evidence that it is needed.

### Unit tests, integration tests, isolation, and cleanup

Unit tests inspect metadata, mapping, and service decisions without a database.
Integration tests use PostgreSQL because SQLite differs in types, constraints,
foreign keys, and transactional DDL. The dedicated `travelops_test` database is
validated by name, migrated to head, truncated before and after tests, and never
shares records with development. Tests deliberately provoke integrity errors
and interrupted writes to prove PostgreSQL enforcement and rollback.

### Deterministic and controlled seeding

Seeding always starts with a fully validated Phase 2 `SyntheticDataset`.
Ordinary seed refuses a non-empty database, making repeated execution safe and
visible. `--replace` explicitly clears and inserts within one transaction.
Reset requires `--confirm` and is blocked when the environment is production.
The same generator seed recreates the same coherent domain dataset.

### Business records versus future workflow checkpoints

Phase 3 stores passengers, flights, bookings, disruptions, policies, and cases.
It does not store an agent's current node, tool history, retry count, or pending
approval. Those future workflow checkpoints have different lifecycles and
belong to Phase 8 even if PostgreSQL eventually stores both kinds of data.

## Decisions I made

- [D-017](../decisions.md#d-017--use-synchronous-sqlalchemy-with-explicit-mapping)
  selects synchronous SQLAlchemy and keeps records separate from the domain.
- [D-018](../decisions.md#d-018--use-a-normalized-postgresql-schema-with-typed-disruption-details)
  selects normalized tables and typed disruption detail columns.
- [D-019](../decisions.md#d-019--let-alembic-own-schema-history)
  makes reviewed migrations the only schema-creation mechanism.
- [D-020](../decisions.md#d-020--place-transactions-around-application-workflows)
  defines the repository, service, and unit-of-work responsibilities.
- [D-021](../decisions.md#d-021--make-development-data-management-explicit-and-safe)
  records the controlled seed, replace, reset, and isolated-test behavior.

## Tests and demonstrations

- Metadata tests inspect every table, relationship, key, timestamp, constraint,
  and index defined by the ORM.
- Mapping tests round-trip every domain type and reject corrupted records.
- Alembic integration testing downgrades the isolated database to zero and
  upgrades it to revision `0001` before inspecting tables and timestamps.
- Constraint tests provoke duplicate keys, missing references, duplicate
  segment order, incoherent disruption references, invalid typed details, and
  broken recovery cases in real PostgreSQL.
- Repository tests persist all ten cases, verify exact table counts, retrieve a
  complete case, clean all records, and prove caller-controlled rollback.
- Service and unit-of-work tests prove seed, refusal, atomic replacement,
  production reset blocking, complete retrieval, commit, and rollback.
- CLI tests cover seed, replace, reset confirmation, counts, safe errors, and
  missing cases. Manual commands demonstrated the same flow in development.
- The final cross-phase gate passed all 153 tests without warnings, Ruff lint
  and format checks, strict mypy, locked synchronization, package import, wheel
  and source builds, Compose validation, PostgreSQL health, and a real-socket
  `GET /health` request.

## What failed or surprised me

- The existing desktop PostgreSQL already used port 5432, so Compose maps the
  isolated container to `127.0.0.1:55432`.
- PostgreSQL 18 uses `/var/lib/postgresql` for the container volume layout.
- `pg_isready` briefly reported no response while the new container was still
  starting; the configured health check then became healthy normally.
- Entering a password at the `psql` prompt was initially mistaken for an SQL
  command. `\password travelops` is the interactive password-change command.
- The local PowerShell version did not support `Read-Host -MaskInput` as used,
  so subsequent instructions use `Get-Credential` and avoid echoing secrets.
- Alembic autogeneration produced the starting point, but the revision still
  required human review and formatting before it became schema history.

## Remaining limitations

- Phase 3 adds no booking, flight, disruption, policy, or case HTTP routes.
- It adds no Phase 4 operational tools and gives no agent direct database access.
- There is no workflow checkpoint, audit-write, authorization, background job,
  cache, queue, frontend, model, LangChain, or LangGraph integration.
- Reset is intentionally a development/test operation, not a production data
  lifecycle system.
- The PostgreSQL service is local development infrastructure, not a production
  deployment design.
