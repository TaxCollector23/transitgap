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
    try {
      const response = await fetch(path, {signal:controller.signal,cache:"no-store"});
      if (response.status < 500 && response.status !== 429) return await json(response);
      last = Error("The routing service is starting or temporarily unavailable.");
    } catch (error) { last=error; }
    finally { window.clearTimeout(timer); }
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
export async function plannerData(): Promise<{
  coverage: Coverage;
  stops: Stop[];
}> {
  if (PREPARED) {
    try {
      const r = await fetch("/bootstrap.json");
      if (r.ok) {
        const data = await r.json();
        if (data.coverage && Array.isArray(data.stops) && data.stops.length)
          return data;
      }
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
  const data = await prepared(
    "/study-summary.json",
    `/gaps?limit=${limit}`,
    signal,
  );
  return { ...data, features: data.features.slice(0, limit) };
}
export function stopAccess(id: string, signal?: AbortSignal) {
  return prepared(
    `/studies/${encodeURIComponent(id)}.json`,
    `/stops/${encodeURIComponent(id)}/access`,
    signal,
  );
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
  routingWarmup = serviceJSON(`${API}/health`)
    .then(data => Boolean(data.ready))
    .catch(() => false)
    .finally(() => { routingWarmup = null; });
  return routingWarmup;
}
