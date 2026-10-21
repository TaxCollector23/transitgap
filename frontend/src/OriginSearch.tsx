import { useId, useState } from "react";
import { API } from "./data";

type Result = { name: string; latitude: number; longitude: number };

export default function OriginSearch({
  onChoose,
  label = "Address or place",
  placeholder = "Street address or place",
}: {
  onChoose: (point: [number, number], name: string) => void;
  label?: string;
  placeholder?: string;
}) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [items, setItems] = useState<Result[]>([]);
  return (
    <div className="origin-search">
      <form
        className="inline-search"
        role="search"
        onSubmit={async (e) => {
          e.preventDefault();
          if (query.trim().length < 3) {
            setMessage("Type at least 3 characters of an address or place.");
            return;
          }
          setBusy(true);
          setMessage("");
          try {
            const r = await fetch(`${API}/geocode`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ query }),
            });
            const data = await r.json();
            if (!r.ok) throw Error(typeof data.detail === "string" ? data.detail : "Address search is unavailable right now.");
            setItems(data.results);
            if (!data.results.length)
              setMessage("No address found inside the supported area. Try a nearby street or landmark.");
          } catch (error) {
            setMessage(
              error instanceof TypeError
                ? "Address search can't connect right now. You can use your location or choose on the map."
                : error instanceof Error ? error.message : "Address search is unavailable right now.",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="sr-only" htmlFor={`${id}-query`}>{label}</label>
        <input
          id={`${id}-query`}
          className="text-input"
          value={query}
          placeholder={placeholder}
          onChange={(e) => setQuery(e.target.value)}
          maxLength={200}
          autoComplete="street-address"
        />
        <button className="button" disabled={busy}>
          {busy ? "Searching…" : "Search"}
        </button>
      </form>
      <p className="field-hint" role="status">
        {message || "Address searches are sent to OpenStreetMap’s Nominatim service."}
      </p>
      {items.length > 0 && (
        <ul className="address-results" aria-label="Address results">
          {items.map((item) => (
            <li key={`${item.latitude},${item.longitude}`}>
              <button
                type="button"
                className="list-row"
                onClick={() => {
                  onChoose([item.latitude, item.longitude], item.name.split(",").slice(0, 2).join(","));
                  setItems([]);
                  setQuery("");
                }}
              >
                {item.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      <details className="quiet-details">
        <summary>Enter coordinates instead</summary>
        <form
          className="coordinate-form"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            const lat = Number(data.get("latitude"));
            const lon = Number(data.get("longitude"));
            onChoose([lat, lon], `${lat.toFixed(5)}, ${lon.toFixed(5)}`);
          }}
        >
          <label>
            Latitude
            <input className="text-input" name="latitude" type="number" step="any" min="-90" max="90" required />
          </label>
          <label>
            Longitude
            <input className="text-input" name="longitude" type="number" step="any" min="-180" max="180" required />
          </label>
          <button className="button">Use coordinates</button>
        </form>
      </details>
    </div>
  );
}
