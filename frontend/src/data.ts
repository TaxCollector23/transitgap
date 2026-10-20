import type { Coverage, Stop } from "./types";
export const API =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? "" : "http://localhost:8000");
export const PREPARED = import.meta.env.PROD && !import.meta.env.VITE_API_URL;
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
  const [h, c, s] = await Promise.all([
    fetch(`${API}/health`, { keepalive: true, cache: "no-store" }),
    fetch(`${API}/coverage`),
    fetch(`${API}/stops`),
  ]);
  const health = await json(h);
  if (!health.ready)
    throw Error(
      health.error || "Transit and walking data could not be loaded.",
    );
  return { coverage: await json(c), stops: (await json(s)).stops };
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
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 60000);
  routingWarmup = fetch(`${API}/health`, {
    keepalive: true,
    cache: "no-store",
    signal: controller.signal,
  })
    .then(json)
    .then((data) => Boolean(data.ready))
    .catch(() => false)
    .finally(() => {
      window.clearTimeout(timeout);
      routingWarmup = null;
    });
  return routingWarmup;
}
