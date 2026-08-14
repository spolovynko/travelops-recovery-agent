import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./shell";
import { CaseQueuePage } from "../features/cases/CaseQueuePage";
import { RecoveryWorkspacePage } from "../features/recovery/RecoveryWorkspacePage";
import { EvaluationSummaryPage } from "../features/evaluations/EvaluationSummaryPage";

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <Navigate to="/cases" replace /> },
      { path: "/cases", element: <CaseQueuePage /> },
      { path: "/cases/:caseId", element: <RecoveryWorkspacePage /> },
      { path: "/evaluations", element: <EvaluationSummaryPage /> },
      { path: "*", element: <Navigate to="/cases" replace /> },
    ],
  },
]);
