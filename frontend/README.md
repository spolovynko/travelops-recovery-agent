# TravelOps operator dashboard

This directory contains the Phase 5 React and TypeScript operator dashboard.
It is a browser client for the versioned FastAPI recovery endpoints; it does
not duplicate recovery rules or write booking state.

## Run locally

Start FastAPI from the repository root:

```powershell
uv run uvicorn travelops_recovery_agent.api.app:app --reload
```

In a second terminal, start Vite:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173/cases`. During development, Vite proxies `/api`
and `/health` requests to `http://127.0.0.1:8000`.

## Structure

```text
src/
|-- api/          # Typed API models and the HTTP boundary
|-- app/          # Router, query client, providers, and shell
|-- components/   # Reusable loading, error, and status UI
|-- features/     # Case queue and recovery workspace
|-- styles/       # Global responsive visual system
`-- test/         # Shared component-test setup and fixtures
e2e/              # Playwright workflow coverage
```

## Quality checks

```powershell
npm run format:check
npm run typecheck
npm run lint
npm test
npm run build
npm run test:e2e
```

The UI workflow and backend boundary are documented with diagrams in
[`../docs/notes/phase-5.md`](../docs/notes/phase-5.md).
