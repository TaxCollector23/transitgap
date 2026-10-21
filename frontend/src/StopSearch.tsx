import { useId, useMemo, useRef, useState } from "react";
import {
  type AgencyFilter,
  type Place,
  distanceM,
  formatDistance,
  normalize,
} from "./format";

const FILTERS: Array<{ value: AgencyFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "vta", label: "VTA" },
  { value: "caltrain", label: "Caltrain" },
  { value: "bart", label: "BART" },
];

type Props = {
  places: Place[];
  selected: Place | null;
  reference: [number, number] | null;
  referenceLabel: string;
  disabled?: boolean;
  onSelect: (place: Place) => void;
  onClear: () => void;
};

export default function StopSearch({
  places,
  selected,
  reference,
  referenceLabel,
  disabled,
  onSelect,
  onClear,
}: Props) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [agency, setAgency] = useState<AgencyFilter>("all");

  const results = useMemo(() => {
    const terms = normalize(query).split(" ").filter(Boolean);
    return places
      .filter((place) => agency === "all" || place.agency === agency)
      .map((place) => {
        const haystack = normalize(`${place.name} ${place.description}`);
        const name = normalize(place.name);
        const matches = terms.every((term) => haystack.includes(term));
        return {
          place,
          matches,
          prefix: terms.length > 0 && name.startsWith(terms.join(" ")),
          distance: reference
            ? distanceM(reference, [place.latitude, place.longitude])
            : null,
        };
      })
      .filter((item) => item.matches)
      .sort(
        (a, b) =>
          Number(b.prefix) - Number(a.prefix) ||
          (a.distance ?? 0) - (b.distance ?? 0) ||
          a.place.name.localeCompare(b.place.name),
      )
      .slice(0, terms.length ? 8 : 5);
  }, [places, query, agency, reference]);

  const choose = (place: Place) => {
    onSelect(place);
    setQuery("");
    setOpen(false);
  };

  if (selected) {
    return (
      <div className="field-value">
        <span className="field-value-text">
          <strong>{selected.name}</strong>
          <span>{selected.description}</span>
        </span>
        <button
          type="button"
          className="text-button field-change"
          onClick={() => {
            onClear();
            setOpen(true);
            requestAnimationFrame(() => inputRef.current?.focus());
          }}
        >
          Change<span className="sr-only"> destination</span>
        </button>
      </div>
    );
  }

  const listId = `${id}-results`;
  const activeId = open && results[active] ? `${id}-option-${active}` : undefined;
  return (
    <div className="stop-search">
      <div className="agency-filter" role="radiogroup" aria-label="Transit agency">
        {FILTERS.map((filter) => (
          <label key={filter.value}>
            <input
              type="radio"
              name={`${id}-agency`}
              value={filter.value}
              checked={agency === filter.value}
              onChange={() => {
                setAgency(filter.value);
                setActive(0);
                setOpen(true);
              }}
            />
            <span>{filter.label}</span>
          </label>
        ))}
      </div>
      <input
        ref={inputRef}
        id="stop-search"
        className="text-input"
        type="text"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={activeId}
        aria-describedby={`${id}-hint`}
        placeholder="Station or stop name"
        autoComplete="off"
        disabled={disabled}
        value={query}
        onFocus={() => setOpen(true)}
        onBlur={(event) => {
          if (!event.currentTarget.parentElement?.contains(event.relatedTarget as Node))
            setOpen(false);
        }}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setActive((value) => Math.min(value + 1, results.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((value) => Math.max(value - 1, 0));
          } else if (event.key === "Enter" && open && results[active]) {
            event.preventDefault();
            choose(results[active].place);
          } else if (event.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      <p className="field-hint" id={`${id}-hint`}>
        {query
          ? `${results.length ? results.length : "No"} matching ${results.length === 1 ? "place" : "places"}`
          : `Type a name, or pick from places closest to ${referenceLabel}.`}
      </p>
      <ul
        className="stop-results"
        id={listId}
        role="listbox"
        aria-label="Transit stops and stations"
        hidden={!open}
      >
        {results.map(({ place, distance }, index) => (
          <li
            key={place.key}
            id={`${id}-option-${index}`}
            role="option"
            aria-selected={index === active}
            className={`stop-option ${index === active ? "is-active" : ""}`}
            onMouseDown={(event) => event.preventDefault()}
            onMouseEnter={() => setActive(index)}
            onClick={() => choose(place)}
          >
            <span className="stop-option-name">
              <strong>{place.name}</strong>
              <span>{place.description}</span>
            </span>
            {distance != null && (
              <span className="stop-option-distance">{formatDistance(distance)}</span>
            )}
          </li>
        ))}
        {results.length === 0 && (
          <li className="stop-empty" role="option" aria-disabled="true" aria-selected="false">
            No matching stops{agency !== "all" ? " for this agency" : ""}. Check the spelling or choose All.
          </li>
        )}
      </ul>
    </div>
  );
}
