import { useState } from "react";
import { API } from "./data";
export default function OriginSearch({
  onChoose,
}: {
  onChoose: (point: [number, number]) => void;
}) {
  const [query, setQuery] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const [items, setItems] = useState<
    Array<{ name: string; latitude: number; longitude: number }>
  >([]);
  return (
    <details className="plain-details">
      <summary>Search an address</summary>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setMessage("");
          try {
            const r = await fetch(`${API}/geocode`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ query }),
            });
            const data = await r.json();
            if (!r.ok) throw Error(data.detail || "Search unavailable");
            setItems(data.results);
            if (!data.results.length)
              setMessage("No address found inside the supported area.");
          } catch (error) {
            setMessage(
              error instanceof Error ? error.message : "Search unavailable",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <label htmlFor="address-query">Address or place</label>
        <input
          id="address-query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          minLength={3}
          maxLength={200}
          required
          autoComplete="off"
        />
        <button className="button" disabled={busy}>
          {busy ? "Searching…" : "Search"}
        </button>
      </form>
      <details className="plain-details"><summary>Enter coordinates instead</summary><form onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); onChoose([Number(data.get("latitude")), Number(data.get("longitude"))]); }}><label>Starting latitude<input name="latitude" type="number" step="any" min="-90" max="90" required /></label><label>Starting longitude<input name="longitude" type="number" step="any" min="-180" max="180" required /></label><button className="button">Use coordinates</button></form></details>
      <p>
        Search text goes to OpenStreetMap’s Nominatim service. Choose on the map
        if you prefer not to share an address.
      </p>
      {message && <p role="status">{message}</p>}
      <div className="address-results">
        {items.map((item) => (
          <button
            className="list-row"
            key={`${item.latitude},${item.longitude}`}
            onClick={() => {
              onChoose([item.latitude, item.longitude]);
              setItems([]);
              setQuery("");
            }}
          >
            {item.name}
          </button>
        ))}
      </div>
    </details>
  );
}
