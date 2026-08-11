# Phase 1 notes — API, configuration, and logging

## What this phase shipped

Phase 1 added:

- A FastAPI application factory in [`api/app.py`](../../src/travelops_recovery_agent/api/app.py)
- A typed `GET /health` response and generated OpenAPI contract
- Validated settings in [`core/config.py`](../../src/travelops_recovery_agent/core/config.py)
- Per-request IDs and HTTP middleware in [`api/middleware.py`](../../src/travelops_recovery_agent/api/middleware.py)
- Request-local context in [`core/context.py`](../../src/travelops_recovery_agent/core/context.py)
- Explicit JSON logging in [`core/logging.py`](../../src/travelops_recovery_agent/core/logging.py)
- In-process API, configuration, request-ID, logging, and secret-safety tests

The application can be started with:

```powershell
uv run --locked uvicorn travelops_recovery_agent.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

## How it works

The real-socket request flow is:

```text
HTTP client
    → TCP connection to Uvicorn
    → parsed HTTP request
    → ASGI call into FastAPI
    → request-ID middleware
    → /health route
    → typed JSON response
    → middleware response header and JSON log
    → HTTP response to the client
```

`create_app()` loads or accepts a `Settings` instance, explicitly configures the application logger, creates FastAPI, registers middleware, and defines the health route. Uvicorn's `--factory` option calls this function instead of importing a preconstructed global application.

The middleware creates one UUID, stores it in a `ContextVar`, calls the route, adds the same value to `X-Request-ID`, emits a structured completion event, and resets the context in `finally`. Concurrent asynchronous requests therefore do not share request IDs.

## Concepts I can explain

### TCP, HTTP, ASGI, Uvicorn, and FastAPI

- **TCP** provides the ordered network connection between client and server. It knows about bytes and connections, not routes or JSON.
- **HTTP** defines request and response messages: method, path, headers, status, and body.
- **ASGI** is the Python interface through which an async server and application exchange HTTP events.
- **Uvicorn** listens on a TCP socket, parses HTTP, and translates network activity into ASGI calls.
- **FastAPI** routes ASGI requests to Python functions, validates data, serializes responses, and generates OpenAPI.

Each layer has a separate responsibility. FastAPI does not open the development socket itself, and Uvicorn does not implement the `/health` behavior.

### Why use an application factory

A module-level `app = FastAPI()` would construct shared state during import. `create_app()` instead makes creation explicit and repeatable. Tests can create isolated applications with injected settings, Uvicorn can create the real application with `--factory`, and later phases can assemble different dependencies without import-time mutation.

This is a small form of dependency injection: the factory accepts `Settings | None`. A caller can supply a known settings object; otherwise the factory constructs validated settings from the environment. The application uses what it receives instead of locating hidden global configuration.

### Configuration sources and precedence

The active precedence is:

```text
Explicit Settings constructor value
    → TRAVELOPS_* environment variable
    → declared default
```

Constructor values make tests and explicit assembly predictable. Environment variables configure a deployed process without editing source. Defaults make local startup small. Automatic `.env` loading is intentionally absent, so the current source order remains easy to see.

`Environment` and `LogLevel` enums reject unknown values at settings construction. Validation happens before the HTTP application begins serving, which turns a late, ambiguous runtime problem into an early configuration error.

`service_token` uses Pydantic's `SecretStr`. Its normal string and object representations are masked. Code can still reveal it deliberately with `get_secret_value()`, so the type reduces accidental exposure rather than making disclosure impossible. Request logs never serialize the settings object or token.

### Liveness versus readiness

`GET /health` is a liveness check: a successful response shows that this application process can handle HTTP. Readiness would answer whether required dependencies are available for useful work. Phase 1 has no database or external operational service, so inventing readiness checks would communicate evidence that does not exist.

### In-process tests versus a real socket

FastAPI's test client calls the ASGI application in the same Python process. It is fast and deterministic and verifies routing, schemas, middleware, headers, and responses without reserving a port.

The Uvicorn demonstration provides different evidence: an actual server bound `127.0.0.1:8000`, accepted a TCP connection, parsed HTTP, invoked the factory, and returned `/health` and `/openapi.json`. Both checks matter; neither replaces the other.

### Structured logging

A log event is structured data about something that happened. Formatting determines how that event is encoded. The custom formatter emits JSON containing timestamp, severity, logger, message, request ID, method, path, status, and duration when applicable. A log collector can parse fields directly instead of extracting them from prose.

The module does not call `basicConfig()` or attach handlers during import. `configure_logging()` is invoked explicitly by the application factory and configures only the `travelops_recovery_agent` logger hierarchy. Importing a reusable module therefore does not unexpectedly reconfigure unrelated application logging.

### Request IDs

A request ID connects the response seen by a caller to the corresponding server log. `ContextVar` provides a request-local slot that logging can read without passing the ID through every function signature.

The ID is correlation metadata only. It does not authenticate a caller, authorize an operation, prove that logs are genuine, or replace distributed tracing. Phase 1 generates IDs internally rather than trusting caller-provided identifiers.

### Configuration and code boundaries

- `pyproject.toml` configures packaging, dependencies, pytest, Ruff, mypy, and building.
- `core/config.py` validates values that may vary between application environments.
- `core/logging.py` defines application logging mechanics but does nothing during import.
- Middleware applies shared HTTP behavior to every route.
- API schemas describe HTTP data, while routes implement HTTP behavior.
- Uvicorn is process startup infrastructure and remains outside application modules.

## Decisions I made

- [D-011](../decisions.md#d-011--construct-the-api-with-an-application-factory) selects explicit application construction and settings injection.
- [D-012](../decisions.md#d-012--generate-request-ids-in-middleware) selects server-generated UUIDs, middleware, and `ContextVar` isolation.
- [D-013](../decisions.md#d-013--emit-application-logs-as-json) selects explicit standard-library JSON logging on the application logger hierarchy.
- API response schemas live separately from construction code, while one health route remains in `app.py` until more routes justify another layer.

## Tests and demonstrations

- Settings tests cover defaults, environment overrides, constructor precedence, invalid values, and masked secrets.
- API tests cover injected settings, `/health`, OpenAPI, UUID response headers, log correlation, and absence of secrets in request logs.
- Twelve tests passed in-process.
- The real Uvicorn server returned `/health`, `X-Request-ID`, and an OpenAPI document containing `/health`.
- Ruff lint and format checks passed.
- Strict mypy found no issues in twelve source files.
- The installed package imported from `src/travelops_recovery_agent`.
- The wheel and source distribution built successfully.

## What failed or surprised me

- The first real-socket request failed because Uvicorn was not running. Starting the server in one terminal and keeping it active made the second terminal's request succeed. The failure distinguished an unreachable TCP listener from an application response error.
- Deferred formatting exposed inconsistent Windows line endings and one import-order issue. Ruff normalized both, and `.gitattributes` now preserves LF for project source and configuration across Windows checkouts.
- Strict mypy required tests to wrap secret constructor values explicitly in `SecretStr`, even though Pydantic would convert raw strings at runtime. Static and runtime input contracts are related but not identical.
- Starlette warned that its compatibility path using `httpx` was deprecated. The development dependency was changed to the supported `httpx2` package, the lockfile was regenerated, and all tests then passed without warnings.

## Remaining limitations

- The API exposes only liveness and OpenAPI.
- There is no readiness dependency to inspect yet.
- Request IDs correlate one process's logs; distributed trace propagation is not implemented.
- Logging has no external collector, rotation policy, or sensitive-data classification framework.
- The optional service token demonstrates secret handling but is not used for authentication or integration.
- There is no database, airline domain, synthetic data, frontend, agent framework, model integration, authentication, or Docker addition.

## Commands

```powershell
# Synchronize
uv sync --locked --all-groups

# Import
uv run --locked python -c "import travelops_recovery_agent; print(travelops_recovery_agent.__file__)"

# Test and quality gates
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked python -m build --no-isolation

# Start the real server
uv run --locked uvicorn travelops_recovery_agent.api.app:create_app --factory --host 127.0.0.1 --port 8000

# From another PowerShell terminal
$response = Invoke-WebRequest http://127.0.0.1:8000/health
$response.StatusCode
$response.Content
$response.Headers["X-Request-ID"]

$openApi = Invoke-RestMethod http://127.0.0.1:8000/openapi.json
$openApi.info.title
$openApi.paths.PSObject.Properties.Name
```
