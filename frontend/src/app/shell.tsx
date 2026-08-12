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
        <div className="environment">
          <span aria-hidden="true">●</span> Synthetic operations
        </div>
      </header>
      <main id="main-content">
        <Outlet />
      </main>
    </div>
  );
}
