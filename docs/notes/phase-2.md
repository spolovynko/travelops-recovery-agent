# Phase 2 notes — airline domain and synthetic cases

## What this phase shipped

Phase 2 added:

- Immutable typed domain models for passengers, flights, itinerary segments,
  bookings, disruptions, policies, and recovery cases
- Construction-time and cross-record invariants with explicit validation errors
- Timezone-aware flight, disruption, and dataset timestamps
- A versioned synthetic dataset with generator, seed, timestamp, and provenance
  metadata
- Ten reviewed scenarios covering delays, cancellations, missed connections,
  connecting journeys, and group bookings
- A deterministic generator using a local `random.Random(seed)` instance
- Stable UTF-8 JSON serialization and validated loading
- Standard-library CLI commands for generation and validation
- Domain, aggregate, serialization, generator, determinism, and CLI tests

Generate and validate a dataset with:

```powershell
uv run --locked python -m travelops_recovery_agent.data.cli generate `
  --seed 42 `
  --output synthetic-cases.json

uv run --locked python -m travelops_recovery_agent.data.cli validate `
  synthetic-cases.json
```

## How it works

The flow is:

```text
Explicit seed
    → local random generator
    → reviewed scenario blueprints
    → typed domain objects
    → aggregate relationship validation
    → stable JSON bytes
    → CLI output file
    → load and validate through the same aggregate
```

[`domain/models.py`](../../src/travelops_recovery_agent/domain/models.py)
defines the airline facts and rules. It does not import FastAPI, a database,
the CLI, or the generator.

[`data/dataset.py`](../../src/travelops_recovery_agent/data/dataset.py) gathers
the domain objects into one versioned aggregate. It rejects duplicate IDs,
missing passengers or flights, broken itineraries, incoherent disruptions,
unsupported policies, and recovery cases whose references do not belong
together.

[`data/generator.py`](../../src/travelops_recovery_agent/data/generator.py)
turns ten reviewed blueprints into a coherent dataset. The seed varies safe
fictional attributes such as passenger names without changing each scenario's
reviewed purpose. [`data/cli.py`](../../src/travelops_recovery_agent/data/cli.py)
provides the file boundary without adding another runtime dependency.

## Concepts I can explain

### Entity, value object, aggregate, and invariant

An **entity** has a stable identity across changes. `Passenger`, `Flight`,
`Booking`, and `RecoveryCase` are entities because their IDs identify the same
concept even if descriptive attributes later change.

A **value object** is understood by its value rather than an independent
lifecycle. Airport codes, carrier codes, typed identifiers, and disruption
details act as value objects here. Two equal airport codes mean the same value;
they do not need separate database identities.

An **aggregate** is a boundary that proves a related collection is coherent.
`SyntheticDataset` is the Phase 2 aggregate: it owns the complete collections
needed to determine whether every reference exists and belongs together.

An **invariant** is a rule that must remain true. A flight must arrive after it
departs, a booking must have ordered unique segments, and a missed connection
must affect the segment immediately following its arriving flight.

### Domain model versus API schema versus persistence model

A domain model expresses airline meaning and business rules. An API schema
expresses an HTTP request or response contract. A persistence model expresses
tables, columns, foreign keys, and indexes. They can describe related facts but
serve different boundaries. Phase 2 models do not reuse the Phase 1 health API
schema and do not anticipate Phase 3 SQLAlchemy table structure.

### Why business rules belong in deterministic domain code

Flight ordering, itinerary continuity, disruption consistency, and reference
validity have objective answers. Normal Python and Pydantic can apply those
answers repeatedly, quickly, and without prompts, provider availability, or
model interpretation. Later agents may investigate and explain a case, but they
cannot redefine whether its underlying records are valid.

### Construction validation versus workflow validation

Construction validation rejects an object that is invalid using its own fields.
For example, `Flight` rejects a naive datetime immediately. Relationship or
workflow validation needs surrounding context: `Booking` cannot know whether a
flight ID exists until the dataset supplies the flight collection. The
`validate_itinerary` function and `SyntheticDataset` make that context explicit.

### Deterministic generation and seeded randomness

A deterministic generator produces the same result from the same inputs. The
seed initializes a predictable pseudorandom sequence. Identifiers, scenario
ordering, timestamps, and JSON field order are also stable, so repeated runs
with one seed produce identical bytes.

`Random(seed)` creates a local generator. Calling module-level random functions
would mutate shared process state, allowing unrelated code or test order to
change the dataset. Tests prove that generation leaves global random state
untouched.

### Realistic synthetic data versus arbitrary random data

Realistic synthetic data obeys the relationships and constraints needed by the
product. Arbitrary random data merely combines values. The scenario catalogue
fixes ten meaningful disruption stories, connected routes, affected segments,
and passenger counts. Seeded selection varies reviewed fictional names without
randomizing the business meaning of a case. An LLM or Faker would add
dependencies and variability without improving this small catalogue.

### Dataset versions and provenance

`schema_version` tells a loader which structural contract it is reading.
Generator name and version identify the producer. The seed makes the result
reproducible, while the deterministic timestamp and provenance text explain
that the contents are fictional generated data. A future incompatible format
can use another schema version rather than silently changing version 1.0.

### Stable identifiers, ordering, and serialization

Identifiers use explicit prefixes such as `PAX-`, `FLT-`, `BKG-`, and `CASE-`.
The generator creates them from stable sequence numbers and stores records in a
defined order. Tuples preserve that order, Pydantic serializes fields in model
definition order, serialization uses UTF-8, and one final newline is added.

### Timezone-aware datetimes

A naive datetime contains a date and clock reading but no UTC offset, so two
systems cannot reliably compare it with another location's time. Every Phase 2
datetime must provide timezone information. Python then compares the actual
instants correctly even when consecutive flights use different offsets.

### Relationships in a recovery case

Passengers are referenced by bookings. A booking orders itinerary segments,
and each segment references a flight. A disruption references an affected
segment and flight, with type-specific details. A policy declares supported
disruption types. A recovery case joins one coherent booking, disruption, and
policy. Dataset validation walks this whole chain before accepting the file.

### Why the CLI is a useful boundary

The CLI exercises generation and validation without HTTP, a database, or a
model. People, tests, scripts, and Phase 3 seeding code can all consume the same
stable JSON contract. Exit codes and error messages also make invalid fixtures
visible to automation.

### Direct versus transitive dependencies

FastAPI already depended on Pydantic, but Phase 2 imports Pydantic directly.
Pydantic is therefore declared directly in `pyproject.toml`. Depending only on
FastAPI's transitive choice would hide a real project requirement and could
break if FastAPI changed its dependency graph.

## Decisions I made

- [D-014](../decisions.md#d-014--keep-the-airline-domain-independent) keeps
  domain models separate from API and persistence schemas.
- [D-015](../decisions.md#d-015--validate-a-versioned-dataset-aggregate) places
  cross-record validation in a versioned aggregate.
- [D-016](../decisions.md#d-016--generate-reviewed-scenarios-deterministically)
  selects local seeded randomness, reviewed blueprints, stable JSON, and a
  standard-library CLI.

## Tests and demonstrations

- Domain tests cover identifiers, immutable object construction, timezone
  requirements, flight ordering, booking structure, itinerary continuity,
  disruption details, policy rules, and recovery-case identifiers.
- Dataset tests cover metadata, schema versions, duplicate IDs, every required
  reference, coherent missed connections, stable serialization, round trips,
  malformed JSON, and useful nested error paths.
- Generator tests cover all ten cases, all three required disruption types,
  stable ordering, group bookings, same-seed bytes, different seeds, and global
  random-state isolation.
- CLI tests exercise direct command functions and the installed `python -m`
  entry path for generation, validation, missing files, and malformed JSON.
- The final Phase 2 gate passed 102 tests without warnings, including the
  existing `/health` test. Locked synchronization, package import, Ruff lint,
  Ruff format check, strict mypy over 22 files, identical same-seed SHA-256
  hashes, CLI validation, case counting, and both distribution builds passed.

## What failed or surprised me

- A package-level import was briefly added inside `data/dataset.py`, creating an
  unnecessary circular import path. Removing it restored the intended one-way
  dependency from data code to domain code.
- Ruff preferred `itertools.pairwise()` to slicing and `zip()` for consecutive
  itinerary legs. The helper states the intent directly.
- The missed-flight existence check was found to overlap with the affected-flight
  rule because a missed connection must identify the missed flight as affected.
  This can be simplified without weakening validation.

## Remaining limitations

- There is no PostgreSQL, SQLAlchemy, Alembic, repository, or seeding service.
  Phase 3 will map validated domain data into separate persistence models.
- There are no booking, flight, disruption, or case API routes.
- There is no recovery-option search, seat availability, minimum connection-time
  policy, rebooking execution, UI, operational tool, agent, or LLM integration.
- The dataset is fictional and is not compatible with a real airline system.
