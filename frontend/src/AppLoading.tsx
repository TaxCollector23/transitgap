import { Component, useEffect, useState, type ReactNode } from "react";

type LoadingProps = {
  message?: string;
  detail?: string;
};

export default function AppLoading({
  message = "Loading the route planner…",
  detail = "Getting the map ready for your journey.",
}: LoadingProps) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 10000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="app-loading" role="status" aria-live="polite" aria-atomic="true">
      <div className="app-loading-content">
        <span className="spinner app-loading-spinner" aria-hidden="true" />
        <h1>Opening TransitGap</h1>
        <p className="app-loading-message">{message}</p>
        <p>{detail}</p>
        {slow && (
          <div className="app-loading-recovery">
            <p>This is taking longer than usual. Check your connection or try loading again.</p>
            <button className="button" type="button" onClick={() => window.location.reload()}>
              Reload app
            </button>
          </div>
        )}
        <a href="/">Back to home</a>
      </div>
    </div>
  );
}

export class AppLoadBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="app-loading">
        <div className="app-loading-content" role="alert">
          <h1>The app couldn't load</h1>
          <p>Something prevented the app from opening. Check your connection and reload the app.</p>
          <button className="button" type="button" onClick={() => window.location.reload()}>
            Reload app
          </button>
          <a href="/">Back to home</a>
        </div>
      </main>
    );
  }
}
