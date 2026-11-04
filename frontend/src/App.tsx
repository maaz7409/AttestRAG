import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";

// Recharts is the heaviest dependency, so the dashboard is code-split.
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<ChatPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route
          path="analytics"
          element={
            <Suspense fallback={<div className="page muted">Loading dashboard…</div>}>
              <AnalyticsPage />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
