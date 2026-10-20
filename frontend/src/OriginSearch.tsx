import { useState } from "react";
const API =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? "" : "http://localhost:8000");
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
