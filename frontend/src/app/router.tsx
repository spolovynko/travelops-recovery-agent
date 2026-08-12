import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./shell";
import { CaseQueuePage } from "../features/cases/CaseQueuePage";
import { RecoveryWorkspacePage } from "../features/recovery/RecoveryWorkspacePage";

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <Navigate to="/cases" replace /> },
      { path: "/cases", element: <CaseQueuePage /> },
      { path: "/cases/:caseId", element: <RecoveryWorkspacePage /> },
      { path: "*", element: <Navigate to="/cases" replace /> },
    ],
  },
]);
