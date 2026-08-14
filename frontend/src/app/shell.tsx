import { Link, Outlet } from "react-router-dom";

export function AppShell() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="topbar">
        <Link className="brand" to="/cases" aria-label="TravelOps case queue">
          <span className="brand-mark" aria-hidden="true">
            TO
          </span>
          <span>
            <strong>TravelOps</strong>
            <small>Recovery console</small>
          </span>
        </Link>
        <div className="topbar-actions">
          <nav aria-label="Primary navigation">
            <Link to="/cases">Cases</Link>
            <Link to="/evaluations">Evaluation</Link>
            <Link to="/developer/context">Context</Link>
          </nav>
          <div className="environment">
            <span aria-hidden="true">●</span> Synthetic operations
          </div>
        </div>
      </header>
      <main id="main-content">
        <Outlet />
      </main>
    </div>
  );
}
