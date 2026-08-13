# Phase 3 notes — PostgreSQL persistence and service boundaries

## How to read these notes

This document records the project at the end of Phase 3. Later phases may add
queries, tools, API routes, or workflow state, but the explanations below
describe the persistence foundation introduced in this phase.

Use the note in two ways:

- **Brief review:** read “Phase in brief,” the workflows, and the step summaries.
- **Detailed study:** read the Why, What, How, and Evidence sections under each
  step, followed by the concept guide and glossary.

## Phase in brief

### Purpose

Phase 3 moved the validated Phase 2 airline dataset from memory and JSON files
into PostgreSQL. Its purpose was not merely to save rows. It established clear
boundaries between airline meaning, relational storage, database transactions,
and application workflows so later tools can use durable data without receiving
direct SQL or SQLAlchemy access.

### Result

The phase delivered:

- A reproducible PostgreSQL 18 development service
- Direct and locked SQLAlchemy, Psycopg, and Alembic dependencies
- Separate SQLAlchemy records for every Phase 2 business entity
- A normalized relational schema with explicit keys, constraints, indexes,
  nullability, deletion behavior, and timezone-aware timestamps
- A reviewed Alembic revision that migrates an empty database to revision `0001`
- Explicit domain-to-record and record-to-domain mapping
- An application-owned repository protocol and SQLAlchemy implementation
- A transactional application service and SQLAlchemy unit of work
- Controlled commands for seed, replace, reset, row counts, and complete-case
  retrieval
- Isolated integration tests against real PostgreSQL
- A complete Phase 0–3 quality gate with 153 passing tests

### Deliberate boundary

Phase 3 added storage and service boundaries, not operational tools or product
features. It added no booking or case API routes, frontend, agent loop,
LangChain, LangGraph, LLM, workflow checkpoint, rebooking write, authorization
system, background worker, cache, queue, or production deployment design.

The existing `GET /health` endpoint remained a liveness check. It did not become
a database-readiness endpoint. Phase 4 tools will call application services;
they will not receive database sessions or arbitrary query access.

## Persistence workflow

```mermaid
flowchart LR
    A["Validated Phase 2<br/>SyntheticDataset"] --> B["RecoveryDataService<br/>choose workflow"]
    B --> C["Unit of work<br/>open transaction"]
    C --> D["Repository<br/>domain-oriented operation"]
    D --> E["Explicit mapper<br/>domain ↔ record"]
    E --> F["SQLAlchemy session<br/>track and flush records"]
    F --> G[("PostgreSQL<br/>migrated tables")]
    C -->|"success"| H["Commit all changes"]
    C -->|"failure"| I["Roll back all changes"]
```

The application service decides what one complete operation means. The unit of
work owns its transaction. The repository performs storage operations but does
not commit. Mapping keeps the Pydantic domain independent from SQLAlchemy.

## Schema and migration workflow

```mermaid
flowchart LR
    A["SQLAlchemy declarative<br/>record metadata"] --> B["Alembic autogenerate<br/>starting proposal"]
    B --> C["Review revision 0001<br/>constraints and indexes"]
    C --> D["alembic upgrade head"]
    D --> E[("PostgreSQL schema")]
    E --> F["alembic_version = 0001"]
    F --> G["Integration test:<br/>downgrade to base"]
    G --> D
```

SQLAlchemy metadata describes the intended current model. The Alembic revision
is the durable, reviewed history that changes a real database. Application
startup never calls `metadata.create_all()`.

## Artifact map

| Artifact | Responsibility in Phase 3 |
| --- | --- |
| [`compose.yaml`](../../compose.yaml) | Run an isolated local PostgreSQL 18 service with a persistent volume and health check. |
| [`pyproject.toml`](../../pyproject.toml) | Declare SQLAlchemy, Psycopg, and Alembic as direct runtime dependencies. |
| [`uv.lock`](../../uv.lock) | Record the exact resolved persistence dependency graph. |
| [`core/config.py`](../../src/travelops_recovery_agent/core/config.py) | Load the database URL through secret-safe environment configuration. |
| [`persistence/session.py`](../../src/travelops_recovery_agent/persistence/session.py) | Construct the engine and short-lived synchronous session factory. |
| [`persistence/models.py`](../../src/travelops_recovery_agent/persistence/models.py) | Define relational records, columns, relationships, constraints, and indexes. |
| [`persistence/mapping.py`](../../src/travelops_recovery_agent/persistence/mapping.py) | Translate explicitly between SQLAlchemy records and validated domain models. |
| [`application/models.py`](../../src/travelops_recovery_agent/application/models.py) | Define application-level record counts and the complete recovery-case result. |
| [`application/repositories.py`](../../src/travelops_recovery_agent/application/repositories.py) | Define the domain-oriented repository contract owned by the application. |
| [`persistence/repositories.py`](../../src/travelops_recovery_agent/persistence/repositories.py) | Implement repository operations with SQLAlchemy. |
| [`application/services.py`](../../src/travelops_recovery_agent/application/services.py) | Define safe seed, reset, count, and retrieval workflows. |
| [`persistence/unit_of_work.py`](../../src/travelops_recovery_agent/persistence/unit_of_work.py) | Connect application workflows to one SQLAlchemy transaction. |
| [`alembic.ini`](../../alembic.ini) and [`migrations/`](../../migrations/) | Configure and version explicit schema changes. |
| [`persistence/cli.py`](../../src/travelops_recovery_agent/persistence/cli.py) | Expose development database workflows without embedding SQL. |
| [`tests/integration`](../../tests/integration) | Prove migrations, constraints, repositories, transactions, services, and cleanup against PostgreSQL. |

## Step-by-step implementation

### Step 1 — Add a reproducible PostgreSQL development service

**Why this step was taken**

Phase 3 behavior depends on PostgreSQL-specific timestamps, constraints,
foreign keys, transactions, and schema inspection. Every developer therefore
needs a known database version and connection boundary instead of relying on an
unrecorded desktop installation.

**What was implemented**

`compose.yaml` added one `postgres:18.3-bookworm` service with:

- Database and user defaults of `travelops`
- A required password supplied through `TRAVELOPS_POSTGRES_PASSWORD`
- Host binding `127.0.0.1:55432` to container port `5432`
- A named `postgres-data` volume
- A `pg_isready` health check

Only PostgreSQL was containerized. The Python application continued to run in
the project’s local virtual environment.

**How it was implemented**

Compose variable interpolation supplies the database name, user, and password
at runtime. The password expression fails clearly when it is missing. Binding
to `127.0.0.1` prevents the development port from listening on every network
interface. Port `55432` was selected because desktop PostgreSQL already occupied
the normal host port `5432`.

PostgreSQL 18 stores its managed data below `/var/lib/postgresql`, so the named
volume is mounted at that version-appropriate path. The volume preserves data
across `docker compose down`, while removing and recreating the container
remains safe.

**Evidence**

Compose configuration validated, the container reported healthy, and
`pg_isready -U travelops -d travelops` reported that PostgreSQL was accepting
connections. pgAdmin connected to `127.0.0.1:55432` and displayed the migrated
tables and seeded rows.

### Step 2 — Declare and lock the persistence dependencies

**Why this step was taken**

The project imports SQLAlchemy, Psycopg, and Alembic directly. Depending on an
unrelated package to install them transitively would hide real runtime
requirements and make future dependency changes unpredictable.

**What was implemented**

`pyproject.toml` added compatible ranges for:

- SQLAlchemy 2.x as the ORM and SQL toolkit
- Psycopg 3 with its binary distribution as the PostgreSQL driver
- Alembic 1.x as the schema migration system

`uv.lock` recorded the exact direct and transitive versions selected for this
checkout.

**How it was implemented**

The dependencies were added to the main project dependency list because normal
database workflows require them at runtime. uv resolved the updated graph and
regenerated the lockfile. All later commands used `uv run --locked` so a stale
lockfile could not be changed silently during verification.

**Evidence**

`uv lock --check` and `uv sync --locked --all-groups` succeeded. The installed
package imported successfully, and both wheel and source distribution builds
included the persistence package and migration inputs selected by the build
configuration.

### Step 3 — Add secret-safe database configuration

**Why this step was taken**

A database URL contains connection details and usually a password. Source code,
migrations, normal logs, and test output must not contain a real credential.
Database workflows also need a clear failure when no URL has been configured.

**What was implemented**

`Settings` gained:

```python
database_url: SecretStr | None = None
```

The environment variable name is `TRAVELOPS_DATABASE_URL` because the existing
settings prefix is `TRAVELOPS_`. Database engine construction raises
`DatabaseConfigurationError` when the value is absent.

**How it was implemented**

Pydantic Settings loads the URL from the process environment. `SecretStr`
masks it in `str()` and `repr()`, while the engine factory unwraps it only at
the moment SQLAlchemy needs the actual URL. CLI handling translates database
failures into a generic message rather than printing an exception that might
include connection details.

PowerShell instructions use `Get-Credential` and URL-encode the password before
placing it in the URL. This supports special characters without writing a
credential into a committed `.env` file.

**Evidence**

Configuration tests proved that the URL loads from the environment, remains
masked, and is required for database workflows. Engine tests verified the
driver, host, port, and database without exposing the test password.

### Step 4 — Create the engine and short-lived session factory

**Why this step was taken**

Application code needs one consistent way to create database connectivity and
transaction workspaces. Constructing engines or sessions throughout
repositories and commands would scatter configuration and make lifecycle
management difficult to test.

**What was implemented**

[`persistence/session.py`](../../src/travelops_recovery_agent/persistence/session.py)
added:

- `create_database_engine(settings)`
- `create_session_factory(engine)`
- The typed `SessionFactory` alias
- `DatabaseConfigurationError`

The session factory uses `autoflush=False` and `expire_on_commit=False`.

**How it was implemented**

`create_engine()` receives the secret URL and enables `pool_pre_ping=True`.
The engine owns a pool of reusable connections; the session factory creates a
new short-lived `Session` for each unit of work. Disabling automatic flushes
makes write boundaries explicit. Keeping objects unexpired after commit avoids
surprising reloads when a result is returned after the transaction ends.

This phase selected synchronous SQLAlchemy. The CLI and small application
workflows did not justify introducing asynchronous database control flow.

**Evidence**

Focused tests proved the missing-URL error, Psycopg driver selection, secret
masking, engine binding, session autoflush setting, and expiration setting.
Real transaction tests showed that committed rows persisted and raised
exceptions rolled back.

### Step 5 — Model passengers, flights, bookings, and itinerary segments

**Why this step was taken**

Phase 2 domain models describe valid airline meaning, but PostgreSQL needs a
separate description of tables, columns, identifiers, relationships, and query
structures. Reusing the Pydantic objects as ORM records would couple business
rules to storage mechanics.

**What was implemented**

The first relational group added:

- `passengers`
- `flights`
- `bookings`
- `booking_passengers`
- `itinerary_segments`

Stable Phase 2 identifiers became primary keys. Flight timestamps use
`DateTime(timezone=True)`. Booking passengers use a composite primary key, and
itinerary segments enforce positive, unique order within each booking.

**How it was implemented**

SQLAlchemy 2 declarative records use `Mapped[...]` annotations and
`mapped_column()`. A booking-to-passenger relationship is many-to-many, so the
schema uses the normalized `booking_passengers` association table rather than
storing passenger IDs in a text or JSON column.

One booking has many ordered segments. Each segment references both its booking
and flight. Unique constraints prevent the same flight or sequence from being
used twice within one booking. Flight checks reject identical origin and
destination airports and arrival times that do not follow departure. Route and
foreign-key lookup paths receive deliberate indexes.

**Evidence**

Metadata tests inspect primary keys, foreign keys, deletion behavior,
nullability, timestamp timezone flags, unique constraints, checks, indexes, and
ORM relationships. PostgreSQL tests reject duplicate identifiers, missing
booking-passenger references, and duplicate segment sequence values.

### Step 6 — Model disruptions, policies, and recovery cases

**Why this step was taken**

The remaining Phase 2 entities contain more complex relationships and
type-specific rules. PostgreSQL should complement domain validation by rejecting
obviously incoherent rows even if a bug or external process bypasses the normal
Python construction path.

**What was implemented**

The second relational group added:

- `disruptions`
- `disruption_policies`
- `disruption_policy_types`
- `recovery_cases`

Disruptions store a discriminator plus typed detail columns for delay minutes,
cancellation reason, arriving flight, and missed flight. Policy types use a
normalized ordered child table. Recovery cases reference an existing booking,
disruption, and policy.

**How it was implemented**

Known disruption variants were modeled with typed nullable columns and check
constraints rather than one opaque JSONB document. The discriminator determines
which detail columns must be present and which must be absent. A composite
foreign key requires a disruption’s affected segment and affected flight to be
the same pair stored by the itinerary segment.

Policy type rows preserve the order of applicable disruption types while
preventing duplicates. Recovery-case foreign keys use explicit `RESTRICT`
deletion behavior, and frequently followed case relationships receive indexes.

**Evidence**

Metadata tests inspect all constraints and indexes. Real PostgreSQL integration
tests reject an affected segment/flight mismatch, missing type-specific details,
unsupported relationships, and a recovery case whose referenced rows do not
exist.

### Step 7 — Make Alembic the owner of schema history

**Why this step was taken**

ORM metadata describes the schema expected by the current code, but a durable
database needs an ordered history of how to reach that schema. Automatic table
creation cannot safely explain or review changes to an existing database.

**What was implemented**

Alembic configuration added:

- `alembic.ini` without a committed database credential
- `migrations/env.py` connected to `Settings`, the engine factory, and
  `Base.metadata`
- `migrations/versions/0001_create_business_persistence_schema.py`
- Online and offline migration support
- Type comparison during migration inspection

**How it was implemented**

`alembic init migrations` created the migration environment. Autogeneration
compared `Base.metadata` with the empty database and proposed revision `0001`.
The revision was reviewed to confirm table order, types, keys, checks, indexes,
foreign keys, and downgrade order before it became project history.

The database URL comes from `TRAVELOPS_DATABASE_URL`; it is not stored in
`alembic.ini`. `alembic upgrade head` applies the revision, and PostgreSQL stores
`0001` in `alembic_version`. No application import or startup path calls
`metadata.create_all()`.

**Evidence**

The development database upgraded to revision `0001`. An integration test
downgrades the isolated `travelops_test` database to `base`, confirms that the
business tables are absent, upgrades to `head`, and inspects the recreated
tables, revision, nullability, and timezone-aware columns.

### Step 8 — Map explicitly between records and domain objects

**Why this step was taken**

Persistence records and domain models represent related information but have
different responsibilities. A visible translation boundary prevents SQLAlchemy
mechanics from entering the domain and ensures that data loaded from storage is
still checked against Phase 2 invariants.

**What was implemented**

[`persistence/mapping.py`](../../src/travelops_recovery_agent/persistence/mapping.py)
added record-to-domain and domain-to-record functions for:

- Passenger
- Flight
- Booking and its passenger/segment associations
- Each disruption variant
- Disruption policy and ordered policy types
- Recovery case

`PersistenceMappingError` identifies a stored entity that cannot be rebuilt as
a valid domain object.

**How it was implemented**

Write mapping copies validated domain fields into new SQLAlchemy records. Read
mapping constructs explicit dictionaries and calls the normal Pydantic domain
validators. It sorts ordered child records before rebuilding tuples. The
disruption mapper translates between the domain’s discriminated detail objects
and the schema’s typed nullable columns.

Pydantic `ValidationError` is caught only at this boundary and wrapped with the
stored entity type and identifier. This preserves the cause while producing a
clear persistence-oriented failure.

**Evidence**

Mapping tests round-trip every supported domain type and compare the rebuilt
objects with the originals. Deliberately corrupted records fail clearly instead
of leaking invalid state into application services.

### Step 9 — Define application-owned persistence contracts

**Why this step was taken**

Future tools and APIs need business-oriented operations, not access to a
SQLAlchemy session. If the persistence layer owned the interface, higher-level
application code would depend on database details rather than defining what it
actually requires.

**What was implemented**

The application package added:

- `PersistenceRecordCounts`
- `CompleteRecoveryCase`
- The `RecoveryDataRepository` protocol
- The `RecoveryDataUnitOfWork` protocol and factory type

The repository contract exposes only `counts`, `add_dataset`,
`get_complete_case`, and `clear`.

**How it was implemented**

Python `Protocol` types express the required behavior without importing
SQLAlchemy. The application layer imports domain and dataset types, while the
concrete persistence layer imports and implements the application contract.
This reverses the dependency direction: the technical adapter conforms to the
application’s needs.

The result types are application models because a complete case and persistence
counts are workflow results, not individual domain entities or database rows.

**Evidence**

Strict mypy proved that the SQLAlchemy repository and unit of work satisfy the
application protocols. Application-service tests replace them with small fakes,
demonstrating that workflow behavior can be tested without PostgreSQL.

### Step 10 — Implement the SQLAlchemy repository

**Why this step was taken**

The repository needed to persist one already validated dataset, retrieve one
coherent domain-oriented case, count managed records, and clear controlled data.
It also needed to avoid taking ownership of a larger transaction.

**What was implemented**

`SqlAlchemyRecoveryDataRepository` implements:

- Exact counts for all nine business tables
- Ordered insertion of a validated `SyntheticDataset`
- Complete recovery-case retrieval
- Dependency-safe clearing of managed records

It receives one caller-owned `Session` and never calls `commit()`.

**How it was implemented**

Dataset insertion follows foreign-key dependency order:

1. Passengers, flights, and policies
2. Bookings with passenger and segment associations
3. Disruptions
4. Recovery cases

`flush()` sends each dependency group to PostgreSQL while keeping every group in
the same transaction. Clearing performs bulk deletes in reverse dependency
order. Database cascades remove booking and policy association rows where that
behavior was chosen explicitly.

Complete retrieval uses SQLAlchemy loader options to fetch the booking,
passenger links, passengers, ordered segments, flights, disruption, policy, and
policy types without returning persistence records to the caller.

**Evidence**

Real repository tests persist seed 42 and verify 13 passengers, 20 flights, 10
bookings, 13 booking-passenger links, 20 segments, 10 disruptions, one policy,
three policy types, and 10 recovery cases. They retrieve `CASE-0007`, compare it
with the expected domain aggregate, clear all records, and prove an interrupted
caller transaction leaves the database empty.

### Step 11 — Put transactions around application workflows

**Why this step was taken**

A seed operation writes many related rows. Committing inside repository methods
could preserve early rows even if a later write failed. Transaction ownership
therefore belongs around the complete application operation.

**What was implemented**

`RecoveryDataService` added workflows for:

- Counting managed records
- Seeding only an empty database
- Explicit atomic replacement with `replace=True`
- Resetting only development or test environments
- Retrieving one complete recovery case

`SqlAlchemyRecoveryDataUnitOfWork` opens the session, creates the repository,
commits a successful context, rolls back an exceptional context, and always
closes the session.

**How it was implemented**

The service receives a unit-of-work factory and an `Environment`. It contains no
SQLAlchemy import. Entering the concrete unit of work creates one session and
repository. Exiting normally attempts one commit. A workflow exception or
commit failure triggers rollback, and `finally` closes the session.

Ordinary seeding checks counts and raises `DatabaseNotEmptyError` rather than
mixing datasets. Replacement clears and inserts inside the same unit of work.
Reset checks the environment before even opening a transaction and raises
`UnsafeDatabaseResetError` in production.

**Evidence**

Seven fast service tests prove empty seeding, non-empty refusal, atomic replace,
production reset blocking, development/test reset, counts, and retrieval.
PostgreSQL tests prove commit behavior and deliberately interrupt a seed to
confirm that no partial records remain.

### Step 12 — Add safe database workflow commands

**Why this step was taken**

Developers need a repeatable way to demonstrate and manage local synthetic data
without writing SQL manually or bypassing application safety rules. The command
line is also a useful adapter before later APIs and tools exist.

**What was implemented**

[`persistence/cli.py`](../../src/travelops_recovery_agent/persistence/cli.py)
added:

- `seed --seed N`
- `seed --seed N --replace`
- `reset --confirm`
- `counts`
- `show-case CASE-ID`

**How it was implemented**

The CLI constructs settings, engine, session factory, unit-of-work factory, and
application service. Each subcommand delegates behavior to the service; the CLI
contains no SQL and never imports persistence record classes.

The reset path requires explicit confirmation before constructing the service.
The service independently blocks production reset. Expected configuration,
validation, and safe workflow errors produce useful messages. SQLAlchemy errors
are translated into a generic database failure so a credential-bearing URL or
internal stack trace is not printed. The engine is disposed in `finally`.

**Evidence**

Seven CLI tests prove seed generation, explicit replacement, non-empty refusal,
reset confirmation, empty reset results, JSON counts, and missing-case handling.
Manual development commands demonstrated refusal, seed-99 replacement, reset,
and a final canonical seed-42 load.

### Step 13 — Retrieve one complete recovery case

**Why this step was taken**

Persisting isolated rows is insufficient for later operational tools. The phase
needed proof that one application query can reconstruct a coherent case with
all information required for investigation.

**What was implemented**

`CompleteRecoveryCase` contains:

- Recovery case
- Booking
- Passengers
- Ordered itinerary flights
- Disruption
- Applicable policy

The repository returns this application result or `None` for an unknown stable
case identifier.

**How it was implemented**

The query starts from `RecoveryCaseRecord` and eagerly loads its related graph.
Joined loading handles direct single-object relationships, while select-in
loading handles collections such as passengers, segments, and policy types.
`unique()` removes duplicate parent rows caused by relationship joins.

Every loaded record passes through explicit mapping. Passenger and flight tuples
follow the booking’s stable relationship order, so callers receive domain
objects rather than an unordered collection of rows.

**Evidence**

Repository and service integration tests retrieve `CASE-0007` with its group of
three passengers and two flights. The CLI prints the complete result as
structured JSON, and pgAdmin shows the underlying related rows in their tables.

### Step 14 — Test against isolated real PostgreSQL

**Why this step was taken**

SQLite cannot prove PostgreSQL timestamp behavior, constraint semantics,
foreign-key enforcement, driver behavior, or migration DDL. Integration tests
must use the same database family as development while remaining unable to
erase development data.

**What was implemented**

The integration test fixtures require `TRAVELOPS_TEST_DATABASE_URL` and verify
that its database name is exactly `travelops_test`. They:

- Apply Alembic migrations to the test database
- Truncate every managed table before and after isolated tests
- Create a session factory bound only to the test engine
- Dispose the engine after the session-scoped test work

Integration suites cover migrations, constraints, repositories, transactions,
application workflows, rollback, and cleanup.

**How it was implemented**

The fixture parses the URL before connecting. A PostgreSQL backend and exact
test database name are mandatory. `TRUNCATE ... CASCADE` clears managed records
in a transaction without altering the schema. The migration test alone moves
the isolated schema down to `base` and back to `head`.

Constraint tests deliberately attempt invalid writes and expect
`IntegrityError`. Transaction tests deliberately raise exceptions after writes
and then inspect the database through a new session.

**Evidence**

The complete suite passed 153 tests without warnings. The integration portion
proved zero-to-head migration, revision tracking, timezone columns, duplicate
key rejection, foreign keys, segment uniqueness, disruption consistency,
complete retrieval, safe seed/replace/reset, atomic rollback, and cleanup.

### Step 15 — Preserve earlier quality gates and record Phase 3 evidence

**Why this step was taken**

A new database layer is not complete if it breaks the package, deterministic
dataset, API liveness contract, formatting, typing, or distribution build that
earlier phases established.

**What was implemented**

Phase 3 updated the README, progress handoff, architectural decisions, roadmap
wording, and these learning notes. The final gate retained all earlier tests and
added persistence-focused linting, typing, build, Compose, database-health, and
real-socket checks.

**How it was implemented**

The full suite ran with the isolated PostgreSQL URL configured. Ruff checked
both lint and canonical format, strict mypy checked source and tests, and the
locked build backend produced both distribution formats. Compose configuration
and `pg_isready` checked the database service. A real Uvicorn process served the
unchanged `/health` endpoint over a TCP socket.

Meaningful persistence choices were recorded as D-017 through D-021, including
their alternatives, consequences, and revisit conditions.

**Evidence**

The final gate reported 153 passing tests, no warnings, clean Ruff lint and
format checks, no strict-mypy issues, successful package import, successful
wheel and source builds, healthy PostgreSQL, Alembic head `0001`, and a real
`GET /health` response with status 200 and a request ID.

## Detailed concept guide

### Domain model versus persistence model versus API schema

A domain model expresses airline meaning and invariants. A persistence model
expresses tables, columns, foreign keys, and indexes. An API schema expresses an
HTTP contract. The three representations may share facts, but they change for
different reasons. Adding a database index should not redefine a valid flight,
and renaming an HTTP response field should not silently migrate a table.

Phase 3 therefore keeps Pydantic domain objects under `domain/`, SQLAlchemy
records under `persistence/`, and the Phase 1 health schema under `api/`.

### ORM, table, row, column, and mapper

A **table** is a named collection of structurally similar rows. A **row** is one
stored record. A **column** is one typed field that every row in the table can
contain. An **ORM** translates between Python objects and relational operations.
A **mapper** records how a class and its attributes correspond to a table and
columns.

SQLAlchemy declarative classes supply mapping metadata and Python record
objects. The ORM reduces repetitive SQL, but it does not choose the correct
schema, transaction boundary, constraint, or business rule automatically.

### Primary keys, foreign keys, constraints, nullability, and indexes

A primary key uniquely identifies a row. A foreign key requires a referenced
row to exist. A unique constraint rejects repeated values or combinations. A
check constraint rejects a row whose values violate a declared expression.
Nullability decides whether absence is permitted.

An index is a separate lookup structure. It can speed selected queries but uses
storage and must be updated on writes. PostgreSQL creates indexes for primary
keys and unique constraints, but it does not automatically index every
referencing foreign-key column, so useful lookup paths were chosen explicitly.

### One-to-many, many-to-many, and association tables

One booking has many itinerary segments: each segment row holds a booking
foreign key. Bookings and passengers are many-to-many: a booking may contain
several passengers, and a passenger identity may appear in several bookings.
The `booking_passengers` association table stores each unique pair.

An association table makes the relationship queryable and enforceable. A JSON
array inside a booking could not provide the same foreign-key guarantee.

### Normalization versus one large JSON document

Normalization stores distinct concepts once and connects them with keys. This
allows PostgreSQL to enforce references, prevent duplicates, and query related
facts without repeatedly parsing a document. A single JSON dataset would be
simple to save but would hide most relational guarantees.

JSONB is reasonable for flexible auxiliary attributes that do not require
stable relational constraints and may evolve independently. The three current
disruption variants are known and operationally important, so typed columns and
checks were the clearer Phase 3 choice.

### Connection, pool, session, transaction, commit, rollback, and atomicity

A database connection is one live communication channel to PostgreSQL. The
engine maintains a pool so ordinary operations can reuse connections. A session
is SQLAlchemy’s workspace for loaded and pending record objects and borrows a
connection when required.

A transaction groups statements. Commit makes the whole successful transaction
durable. Rollback discards it. Atomicity means the operation behaves as one
indivisible change: the seed is fully stored or none of it is stored.

### SQLAlchemy’s identity map

Within one session, SQLAlchemy normally represents one database identity with
one Python record instance. Loading the same row twice therefore returns the
same managed identity instead of two unrelated objects. This helps coordinate
changes, but it is also why sessions should be short-lived workflow contexts
rather than global application state.

### Repository, application service, unit of work, and dependency inversion

A repository hides storage mechanics behind domain-oriented operations. An
application service decides a complete use case, such as safe seeding. A unit of
work binds repositories to one transaction and defines commit or rollback.

Dependency inversion means the higher-level application defines the interfaces
it needs, while SQLAlchemy code implements them. Future tools can depend on the
application service without importing a database engine, session, or record.

### Migration versus `create_all()`

`metadata.create_all()` creates tables matching current code when they are
missing. It does not provide an ordered reviewable history for changing an
existing database. Alembic revisions record explicit transitions. `upgrade`
moves forward, `downgrade` moves backward when supported, and
`alembic_version` records the applied revision.

Production schema changes must be explicit because data may already exist and
multiple application versions may overlap during deployment. Even in this local
phase, testing the real migration path establishes that discipline.

### Database URLs and secret safety

A SQLAlchemy URL identifies the dialect, driver, username, password, host,
port, and database. TravelOps loads it from the environment as `SecretStr`.
Passwords are entered through a masked prompt, URL-encoded, and never committed
to source, migration configuration, or documentation examples as real values.

Masking representation is helpful but not magical encryption. Code must still
avoid logging the unwrapped value or passing credential-bearing exceptions to a
user-facing boundary.

### Synchronous versus asynchronous database access

Synchronous code waits while one database call completes. Async code can yield
control during the wait, which can improve capacity in a highly concurrent
server. It also adds async sessions, awaited operations, and concurrency
lifecycle rules. Phase 3’s small CLI and service workflows favored the simpler
synchronous model. Evidence, not fashion, should justify a later conversion.

### Unit tests versus real-database integration tests

Unit tests check mapping logic, metadata, and application decisions quickly and
without an external process. Integration tests prove that SQLAlchemy, Psycopg,
Alembic, and PostgreSQL behave together. Both are necessary: metadata inspection
cannot prove PostgreSQL will enforce a constraint, while a database test alone
does not isolate a small application decision clearly.

### Test isolation and cleanup

Integration tests use only `travelops_test`, migrate it explicitly, and remove
managed rows before and after a test. This prevents test order from influencing
results and protects the populated `travelops` development database. The name
check fails closed when a URL points somewhere unexpected.

### Deterministic seeding and controlled reset

The generator remains the source of truth. A seed creates the same validated
dataset for the same integer. Ordinary database seeding refuses existing data,
so it cannot silently combine two datasets. Explicit replacement clears and
inserts atomically. Reset requires confirmation and is blocked in production.

### Mapping failures and domain invariants

Database constraints complement domain validation but do not reproduce every
airline invariant. Record-to-domain mapping therefore invokes Pydantic
validation again. A stored row that cannot form a valid domain object raises a
clear `PersistenceMappingError` instead of spreading corrupted business state.

### Business records versus workflow checkpoints

Passengers, flights, bookings, disruptions, policies, and recovery cases are
business records. An agent’s current node, tool history, retry count, or pending
approval is workflow execution state. They have different schemas and
lifecycles. Phase 3 stores only business records; durable agent checkpoints
belong to Phase 8.

## Commands and what each proves

```powershell
# Reproduce the exact Python dependency graph
uv sync --locked --all-groups

# Enter the PostgreSQL password without printing it
$credential = Get-Credential -UserName travelops `
  -Message "Enter the TravelOps PostgreSQL password"
$password = $credential.GetNetworkCredential().Password
$encodedPassword = [uri]::EscapeDataString($password)

# Supply Compose and application configuration in this terminal only
$env:TRAVELOPS_POSTGRES_PASSWORD = $password
$env:TRAVELOPS_DATABASE_URL = `
  "postgresql+psycopg://travelops:{0}@127.0.0.1:55432/travelops" `
  -f $encodedPassword
$env:TRAVELOPS_TEST_DATABASE_URL = `
  "postgresql+psycopg://travelops:{0}@127.0.0.1:55432/travelops_test" `
  -f $encodedPassword
$env:TRAVELOPS_ENVIRONMENT = "development"

# Start the isolated database and prove its health
docker compose up -d postgres
docker compose ps
docker compose exec postgres pg_isready -U travelops -d travelops

# Apply the explicit migration history and inspect the current revision
uv run --locked alembic upgrade head
uv run --locked alembic current

# Load the canonical validated dataset
uv run --locked python -m travelops_recovery_agent.persistence.cli seed --seed 42

# Prove normal repeat seeding refuses to mix datasets
uv run --locked python -m travelops_recovery_agent.persistence.cli seed --seed 42

# Inspect exact row counts and one complete domain-oriented case
uv run --locked python -m travelops_recovery_agent.persistence.cli counts
uv run --locked python -m travelops_recovery_agent.persistence.cli show-case CASE-0007

# Demonstrate explicit atomic replacement
uv run --locked python -m travelops_recovery_agent.persistence.cli seed `
  --seed 99 --replace

# Demonstrate confirmed development reset, then restore the canonical dataset
uv run --locked python -m travelops_recovery_agent.persistence.cli reset --confirm
uv run --locked python -m travelops_recovery_agent.persistence.cli seed --seed 42

# Inspect tables, indexes, and constraints directly inside PostgreSQL
docker compose exec postgres psql -U travelops -d travelops -c "\dt"
docker compose exec postgres psql -U travelops -d travelops -c "\d recovery_cases"
docker compose exec postgres psql -U travelops -d travelops -c `
  "SELECT COUNT(*) FROM recovery_cases;"

# Run focused real-PostgreSQL integration tests
uv run --locked pytest -m integration

# Run all Phase 0–3 behavioral and integration tests
uv run --locked pytest

# Detect configured static source problems
uv run --locked ruff check .

# Verify canonical formatting without editing files
uv run --locked ruff format --check .

# Check strict static typing across source and tests
uv run --locked mypy

# Prove the installed package resolves
uv run --locked python -c "import travelops_recovery_agent; print('import ok')"

# Produce wheel and source distribution with the locked backend
uv run --locked python -m build --no-isolation

# Start the unchanged API liveness service in terminal 1
uv run --locked uvicorn travelops_recovery_agent.api.app:create_app `
  --factory --host 127.0.0.1 --port 8000

# Prove Phase 1 liveness still works from terminal 2
Invoke-WebRequest http://127.0.0.1:8000/health

# Stop PostgreSQL while preserving its named data volume
docker compose down
```

## Problems encountered and lessons learned

### Desktop PostgreSQL already occupied port 5432

The machine already ran PostgreSQL on the normal port. Publishing the Compose
container on the same host port would have failed or connected tools to the
wrong server. The container was bound to `127.0.0.1:55432` while retaining
PostgreSQL’s internal port `5432`.

**Lesson:** A container port and a host port are separate endpoints. Resolve and
document the actual boundary instead of assuming the default host port is free.

### The first readiness probe ran before startup completed

Immediately after container creation, `pg_isready` briefly reported “no
response.” Compose showed the container as starting, and its configured health
check soon moved it to healthy without any data or configuration change.

**Lesson:** Process creation is not the same as service readiness. Health checks
make the transition observable, and a short initial failure is not automatically
a persistent configuration problem.

### PostgreSQL 18 changed the expected volume path

The PostgreSQL 18 container layout uses `/var/lib/postgresql` for the managed
volume. Reusing an older-version path would have made persistence behavior
confusing or incorrect for this image.

**Lesson:** External service versions can change operational filesystem
contracts. Pin the image and verify its version-specific documentation rather
than copying an old Compose example blindly.

### A PowerShell password prompt exposed a compatibility problem

The local PowerShell version did not support the attempted `Read-Host
-MaskInput` invocation as expected, and the password was entered visibly. The
workflow switched to `Get-Credential`, and the development password was changed.

**Lesson:** Secret-safe instructions must be tested in the actual shell. A value
being placed in an environment variable does not help if the input mechanism
already exposed it.

### Text entered at the `psql` prompt was treated as SQL

A password was typed after the `travelops=#` prompt, so `psql` interpreted it as
the start of an SQL statement and changed to the continuation prompt. The
correct interactive password-change command was `\password travelops`.

**Lesson:** Distinguish the operating-system shell, the `psql` client, and SQL
itself. The visible prompt identifies which interpreter currently owns the
input.

### Alembic autogeneration was only a proposal

Alembic generated the first revision from ORM metadata, but the result still
needed review for table order, constraint names, foreign keys, indexes,
timestamp types, and downgrade behavior.

**Lesson:** Autogeneration accelerates migration authorship; it does not make
schema-design decisions or replace human review.

### The final test initially depended on the developer’s environment

The missing-database-URL unit test constructed `Settings()` while the developer
terminal correctly had `TRAVELOPS_DATABASE_URL` set. The test therefore received
a real URL and did not raise the expected error. It was corrected to construct
`Settings(database_url=None)` explicitly.

**Lesson:** A unit test must construct the state it claims to test. Ambient
environment variables should not silently redefine an isolated scenario.

### Windows line endings failed the deferred format gate

Several new files used CRLF line endings. Behavior, lint, and focused typing
were correct, but the repository-wide Ruff format check expected canonical LF
output. The formatter normalized the files at the final gate.

**Lesson:** Formatting is a distinct quality signal. Deferred full checks are
useful, but their failures still need to be resolved before declaring the phase
complete.

### Duplicate test filenames confused strict mypy

Different test directories contained modules with the same basename, such as
`test_models.py` and `test_services.py`. pytest’s import mode could run them,
but strict mypy treated them as duplicate modules. The persistence and
integration files received distinct descriptive names.

**Lesson:** Tooling can map files to modules differently. Test filenames should
remain unambiguous across the complete checked tree, not only within one folder.

## Decisions made

- [D-017](../decisions.md#d-017--use-synchronous-sqlalchemy-with-explicit-mapping)
  selected synchronous SQLAlchemy and explicit record/domain mapping.
- [D-018](../decisions.md#d-018--use-a-normalized-postgresql-schema-with-typed-disruption-details)
  selected normalized tables and typed disruption detail columns instead of an
  opaque dataset or JSONB details document.
- [D-019](../decisions.md#d-019--let-alembic-own-schema-history) made reviewed
  Alembic revisions the only schema-creation and evolution path.
- [D-020](../decisions.md#d-020--place-transactions-around-application-workflows)
  placed commit and rollback around complete application workflows rather than
  inside repositories.
- [D-021](../decisions.md#d-021--make-development-data-management-explicit-and-safe)
  defined ordinary seed refusal, explicit atomic replacement, confirmed
  non-production reset, and isolated test-database naming.
- PostgreSQL alone was containerized because containerizing the application was
  unnecessary for the Phase 3 learning goal.
- Stable Phase 2 identifiers remained primary keys rather than being replaced
  with unrelated database-generated identities.
- `GET /health` remained a liveness contract; database readiness was not added
  without a consumer and operational requirement.
- Phase 4 tools, Phase 8 workflow checkpoints, and all LLM/framework work were
  deliberately excluded.

## Remaining limitations at the Phase 3 boundary

- The API still exposes no passenger, booking, flight, disruption, policy, or
  recovery-case routes.
- No Phase 4 typed operational tool exists yet, and no model or caller receives
  direct repository or database access.
- The schema stores the current synthetic business model, not real airline
  inventory, fares, ticket rules, aircraft rotations, gates, or live statuses.
- There is no authorization, approval, audit-write, idempotent rebooking, or
  production administrative lifecycle.
- There is no workflow checkpoint, background worker, queue, cache, frontend,
  agent loop, LangChain, LangGraph, LLM integration, or model provider.
- The Compose service is a reproducible local dependency, not a production
  high-availability, backup, encryption, monitoring, or deployment design.
- Synchronous access is an intentional current tradeoff, not proof that async
  access will never be useful.
- The reset command is deliberately restricted fixture management, not a
  general database-maintenance interface.

## Glossary

| Term | Meaning in this project |
| --- | --- |
| Alembic | Migration tool that applies ordered, reviewed SQLAlchemy schema revisions. |
| Association table | Relational table representing a many-to-many link; `booking_passengers` joins bookings and passengers. |
| Atomicity | All changes in one transaction succeed together or are all rolled back. |
| Check constraint | PostgreSQL expression that every accepted row must satisfy. |
| Commit | Make all changes in the current successful transaction durable. |
| Connection | One active communication channel between the process and PostgreSQL. |
| Connection pool | Engine-managed collection of reusable database connections. |
| Declarative model | SQLAlchemy class that declares table mapping through typed attributes and metadata. |
| Dependency inversion | Higher-level application code owns interfaces that lower-level SQLAlchemy adapters implement. |
| Domain model | Pydantic representation of airline meaning and invariants, independent of storage. |
| Engine | SQLAlchemy object holding database configuration, dialect behavior, and the connection pool. |
| Flush | Send pending session changes to PostgreSQL without committing the transaction. |
| Foreign key | Constraint requiring a referenced row to exist. |
| Identity map | Session behavior that keeps one managed Python record per database identity. |
| Index | Additional PostgreSQL structure used to accelerate selected lookup paths. |
| Integration test | Test exercising application code together with real PostgreSQL, Psycopg, SQLAlchemy, or Alembic. |
| Mapper | Configuration translating a Python record class and attributes to a relational table and columns. |
| Migration | Versioned transition that changes a database schema explicitly. |
| Normalization | Storing distinct concepts in related tables rather than duplicating them or hiding them in one document. |
| Nullability | Column rule deciding whether a value may be absent. |
| ORM | Object-relational mapper; SQLAlchemy maps Python records to relational operations. |
| Persistence model | SQLAlchemy representation of storage tables, columns, relationships, and constraints. |
| Primary key | Column or column combination uniquely identifying a row. |
| Psycopg | PostgreSQL driver used by SQLAlchemy to communicate with the database. |
| Repository | Domain-oriented storage interface that hides SQLAlchemy and SQL details from callers. |
| Rollback | Discard all uncommitted changes in the current transaction. |
| Row | One stored record in a relational table. |
| Schema | Set of database tables, columns, constraints, indexes, and relationships. |
| Session | Short-lived SQLAlchemy workspace tracking loaded and pending record objects. |
| Stable identifier | Phase 2 business ID preserved as the database identity, such as `CASE-0007`. |
| Transaction | Group of database statements committed or rolled back as one unit. |
| Unit of work | Application transaction boundary that supplies repositories and owns commit, rollback, and session cleanup. |
| Unique constraint | Rule preventing duplicate values or duplicate value combinations. |
