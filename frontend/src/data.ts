import type { Coverage, Stop } from "./types";
export const API =
  (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || "").replace(/\/$/, "") ||
  (import.meta.env.PROD ? "" : "http://localhost:8000");
export const PREPARED = import.meta.env.PROD && !(import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL);
async function json(response: Response) {
  const data = await response.json();
  if (!response.ok)
    throw Error(
      typeof data.detail === "string"
        ? data.detail
        : data.detail?.message || "Data could not be loaded.",
    );
  return data;
}

export async function serviceJSON(path: string) {
  let last: unknown;
  for (let attempt=0; attempt<3; attempt++) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 15000);
    let response: Response | null = null;
    try {
      response = await fetch(path, {signal:controller.signal,cache:"no-store"});
    } catch (error) { last=error; }
    finally { window.clearTimeout(timer); }
    // Do not retry a valid client error or malformed response. Only repeat a
    // network failure, 429, or server error.
    if (response && response.status < 500 && response.status !== 429)
      return json(response);
    if (response) last = Error("The routing service is starting or temporarily unavailable.");
    if (attempt<2) await new Promise(resolve=>window.setTimeout(resolve,800*2**attempt));
  }
  throw last instanceof Error ? last : Error("The routing service could not be reached. Try again.");
}
async function prepared(path: string, fallback: string, signal?: AbortSignal) {
  if (PREPARED) {
    try {
      const r = await fetch(path, { signal });
      if (r.ok) return await r.json();
    } catch (error) {
      if (signal?.aborted) throw error;
    }
  }
  return json(await fetch(`${API}${fallback}`, { signal }));
}
let preparedPlanner: Promise<{coverage: Coverage; stops: Stop[]}> | null = null;
export function preloadPlannerData() {
  if (!PREPARED) return;
  // Start the CDN request alongside the map bundle, not after React mounts it.
  preparedPlanner ??= fetch("/bootstrap.json").then(async response => {
    if (!response.ok) throw Error("Prepared transit data unavailable.");
    const data = await response.json();
    if (!data.coverage || !Array.isArray(data.stops) || !data.stops.length)
      throw Error("Prepared transit data incomplete.");
    return data;
  });
  // A failed preload must remain retryable, and must not reject unhandled.
  void preparedPlanner.catch(() => { preparedPlanner = null; });
}
export async function plannerData(): Promise<{
  coverage: Coverage;
  stops: Stop[];
}> {
  if (PREPARED) {
    try {
      preloadPlannerData();
      return await preparedPlanner!;
    } catch {
      /* Recover through the live API. */
    }
  }
  const health = await serviceJSON(`${API}/health`);
  if (!health.ready)
    throw Error(
      health.error || "Transit and walking data could not be loaded.",
    );
  const [coverage, data] = await Promise.all([serviceJSON(`${API}/coverage`),serviceJSON(`${API}/stops`)]);
  return {coverage,stops:data.stops};
}
export async function studySummary(limit = 10, signal?: AbortSignal) {
  let data: any;
  if (PREPARED) {
    try {
      const response = await fetch("/study-summary.json", { signal });
      if (response.ok) {
        const snapshot = await response.json();
        if (Array.isArray(snapshot.features) && snapshot.features.length) data = snapshot;
      }
    } catch (error) {
      if (signal?.aborted) throw error;
    }
  }
  if (!data) data = await json(await fetch(`${API}/gaps?limit=${limit}`, { signal }));
  return { ...data, features: data.features.slice(0, limit) };
}
export function stopAccess(id: string, signal?: AbortSignal) {
  return prepared(
    `/studies/${encodeURIComponent(id)}.json`,
    `/stops/${encodeURIComponent(id)}/access`,
    signal,
  );
}
export function reachabilityStops() {
  return serviceJSON(`${API}/accessibility/reachability/stops`);
}
export function stopReachability(id: string, profile: string, minutes = 10) {
  const query = new URLSearchParams({ profile, minutes: String(minutes), sample_size: "150" });
  return serviceJSON(`${API}/accessibility/reachability/${encodeURIComponent(id)}?${query}`);
}
export async function civicLetter(id: string) {
  if (PREPARED) {
    const r = await fetch(`/prepared-letters/${encodeURIComponent(id)}.txt`);
    if (r.ok) return r.text();
  }
  const r = await fetch(`${API}/letters/${encodeURIComponent(id)}`);
  if (!r.ok) throw Error("Letter unavailable.");
  return r.text();
}
let routingWarmup: Promise<boolean> | null = null;
export function warmRouting() {
  // StrictMode and overlapping callers share one cold-start request.
  if (routingWarmup) return routingWarmup;
  routingWarmup = (async () => {
    const deadline = Date.now() + 45000;
    while (Date.now() < deadline) {
      try {
        const response = await fetch(`${API}/health/live`, {cache:"no-store", signal:AbortSignal.timeout(Math.min(8000,deadline-Date.now()))});
        if (response.ok) {
          const health = await response.json();
          if (health.ready) return true;
          if (health.error) return false;
        } else if (response.status < 500 && response.status !== 429) return false;
      } catch { /* A cold instance may not have accepted the first request. */ }
      if (Date.now() < deadline) await new Promise(resolve => window.setTimeout(resolve, 1000));
    }
    return false;
  })()
    .finally(() => { routingWarmup = null; });
  return routingWarmup;
}
