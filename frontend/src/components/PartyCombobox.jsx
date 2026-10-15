import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

const MAX = 8;

/** Names that match what's typed: starts-with first, then contains. */
function matches(parties, text) {
  const q = text.trim().toLowerCase();
  if (!q) return parties.slice(0, MAX);
  const starts = [];
  const contains = [];
  for (const p of parties) {
    const name = p.name.toLowerCase();
    if (name.startsWith(q)) starts.push(p);
    else if (name.includes(q)) contains.push(p);
  }
  return [...starts, ...contains].slice(0, MAX);
}

/**
 * A customer (or supplier) field you can type into. It suggests the ones
 * you already have as you type; pick one, or keep typing a new name and
 * carry on: the new one is added when the document is saved.
 *
 * `value` is { id, name }: an id when an existing one is chosen (or typed
 * exactly), only a name when it's new.
 */
export default function PartyCombobox({ parties, value, onChange, kind = "customer", disabled = false, required = false, placeholder }) {
  const { t } = useTranslation();
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  const text = value.name;
  const options = useMemo(() => matches(parties, text), [parties, text]);
  const exact = parties.find((p) => p.name.trim().toLowerCase() === text.trim().toLowerCase());
  const offerNew = text.trim() !== "" && !exact;
  // The list: suggestions, then "Add 'name'" when nothing matches exactly.
  const rows = offerNew ? [...options, { id: null, name: text.trim(), isNew: true }] : options;

  useEffect(() => setActive(0), [text]);
  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function type(name) {
    // An exact name links to the existing one; anything else is new.
    const same = parties.find((p) => p.name.trim().toLowerCase() === name.trim().toLowerCase());
    onChange(same ? { id: same.id, name } : { id: null, name });
    setOpen(true);
  }

  function choose(row) {
    onChange(row.isNew ? { id: null, name: row.name } : { id: row.id, name: row.name });
    setOpen(false);
  }

  function onKeyDown(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) setOpen(true);
      else setActive((i) => Math.min(rows.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter" && open && rows[active]) {
      e.preventDefault(); // choose, don't submit the form
      choose(rows[active]);
    } else if (e.key === "Escape" && open) {
      e.preventDefault();
      setOpen(false);
    }
  }

  const isNew = text.trim() !== "" && !value.id;
  const showList = open && !disabled && rows.length > 0;

  return (
    <div className="relative">
      <input
        ref={inputRef}
        className="input disabled:bg-slate-50 disabled:text-slate-600"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList ? `${listId}-${active}` : undefined}
        autoComplete="off"
        required={required}
        disabled={disabled}
        value={text}
        placeholder={placeholder}
        maxLength={255}
        onChange={(e) => type(e.target.value)}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
        // Let a click on an option land before the list closes.
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          className="absolute inset-x-0 top-full z-30 mt-1 max-h-72 overflow-auto rounded-xl bg-white py-1 text-sm shadow-pop ring-1 ring-zinc-200"
        >
          {rows.map((row, i) => (
            <li
              key={row.id ?? "new"}
              id={`${listId}-${i}`}
              data-index={i}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(row)}
              onMouseEnter={() => setActive(i)}
              className={`flex cursor-pointer items-center gap-2 px-3 py-2.5 ${i === active ? "bg-indigo-50 text-indigo-900" : "text-zinc-800"} ${
                row.isNew ? "border-t border-zinc-100 font-medium text-indigo-700" : ""
              }`}
            >
              {row.isNew ? (
                <>
                  <span aria-hidden="true">+</span>
                  <span className="truncate">{t(`party.addNew.${kind}`, { name: row.name })}</span>
                </>
              ) : (
                <span className="truncate">{row.name}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {isNew && !disabled && !showList && (
        <p className="mt-1.5 text-xs text-indigo-700" role="status">
          {t(`party.willAdd.${kind}`, { name: text.trim() })}
        </p>
      )}
    </div>
  );
}
