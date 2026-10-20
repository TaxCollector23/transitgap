import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import LandingPage from "./LandingPage";
import AppLoading, { AppLoadBoundary } from "./AppLoading";

const App = React.lazy(() => import("./App"));
const page =
  window.location.pathname === "/" ? (
    <LandingPage />
  ) : (
    <AppLoadBoundary>
      <React.Suspense fallback={<AppLoading />}>
        <App />
      </React.Suspense>
    </AppLoadBoundary>
  );
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{page}</React.StrictMode>,
);
