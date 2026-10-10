import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import i18n from "../i18n";
import { Avatar } from "./ui";

export const OPEN_PALETTE_EVENT = "open-command-palette";
export const openCommandPalette = () => window.dispatchEvent(new Event(OPEN_PALETTE_EVENT));

const ACTIONS = [
  ["newDeal", "sales", "/deals?new=1"],
  ["newInvoice", "sales", "/invoices/new"],
  ["newQuote", "sales", "/quotes/new"],
  ["myActivities", "goTo", "/activities"],
  ["pipeline", "goTo", "/deals"],
  ["invoices", "goTo", "/invoices"],
  ["customers", "goTo", "/customers"],
];


const ROUTE = {
  customer: (h) => `/customers/${h.target_id}`,
  contact: (h) => `/customers/${h.target_id}`,
  deal: (h) => `/deals/${h.target_id}`,
  invoice: (h) => `/invoices/${h.target_id}`,
  quote: (h) => `/quotes/${h.target_id}`,
};

function useDebounced(value, ms) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

/**
 * Cmd/Ctrl+K: search every record and jump anywhere. Opened by keyboard,
 * many times a day, so it appears and disappears instantly, with no
 * animation: any motion here would only make it feel slower.
 */
export default function CommandPalette() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const q = useDebounced(query.trim(), 150);

  useEffect(() => {
    const onKey = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((o) => !o);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_PALETTE_EVENT, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_PALETTE_EVENT, onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      // Next frame: the input exists once the portal has rendered.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const { data: hits = [], isFetching } = useQuery({
    queryKey: ["search", q],
    queryFn: () => apiClient.get("/search", { params: { q } }).then((r) => r.data),
    enabled: open && q.length >= 2,
    staleTime: 10_000,
  });

  const items = useMemo(() => {
    if (query.trim().length < 2) {
      const needle = query.trim().toLowerCase();
      return ACTIONS.map(([key, hint, to]) => ({ key: to, to, kind: "action", label: i18n.t(`palette.action.${key}`), hint: i18n.t(`palette.${hint}`) })).filter((a) =>
        a.label.toLowerCase().includes(needle)
      );
    }
    return hits.map((h) => ({ key: `${h.kind}-${h.id}`, kind: h.kind, label: h.title, hint: h.subtitle, to: ROUTE[h.kind](h) }));
  }, [query, hits]);

  useEffect(() => setActive(0), [items.length]);

  if (!open) return null;

  function go(item) {
    setOpen(false);
    navigate(item.to);
  }

  function onKeyDown(event) {
    if (event.key === "Escape") setOpen(false);
    else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter" && items[active]) {
      event.preventDefault();
      go(items[active]);
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-900/30 px-4 pt-[12vh]" onMouseDown={() => setOpen(false)}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("palette.label")}
        className="w-full max-w-xl overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-pop"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-zinc-100 px-4">
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5 shrink-0 text-zinc-400" aria-hidden="true">
            <path fillRule="evenodd" d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.45 4.39l3.08 3.08a.75.75 0 1 1-1.06 1.06l-3.08-3.08A7 7 0 0 1 2 9Z" clipRule="evenodd" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t("palette.placeholder")}
            className="h-14 flex-1 bg-transparent text-base text-zinc-900 outline-none placeholder:text-zinc-400"
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-results"
            aria-activedescendant={items[active] ? `palette-${items[active].key}` : undefined}
          />
          <kbd className="hidden rounded border border-zinc-200 px-1.5 py-0.5 text-[11px] font-medium text-zinc-400 sm:block">Esc</kbd>
        </div>
        <ul id="palette-results" role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
          {items.length === 0 && (
            <li className="px-3 py-8 text-center text-sm text-zinc-500">
              {isFetching || q !== query.trim() ? t("palette.searching") : t("palette.noMatch", { query: query.trim() })}
            </li>
          )}
          {items.map((item, i) => (
            <li
              key={item.key}
              id={`palette-${item.key}`}
              role="option"
              aria-selected={i === active}
              onMouseMove={() => setActive(i)}
              onClick={() => go(item)}
              className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 ${i === active ? "bg-zinc-100" : ""}`}
            >
              {item.kind === "action" ? (
                <span className="flex h-7 w-7 items-center justify-center rounded-md border border-zinc-200 text-zinc-500">→</span>
              ) : (
                <Avatar name={item.label} size="sm" />
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-zinc-900">{item.label}</span>
                {item.hint && <span className="block truncate text-xs text-zinc-500">{item.hint}</span>}
              </span>
              {item.kind !== "action" && <span className="shrink-0 text-xs text-zinc-400">{t(`palette.kind.${item.kind}`)}</span>}
            </li>
          ))}
        </ul>
        <div className="hidden items-center gap-4 border-t border-zinc-100 px-4 py-2 text-[11px] text-zinc-400 sm:flex">
          <span>{t("palette.hintMove")}</span>
          <span>{t("palette.hintOpen")}</span>
          <span>{t("palette.hintToggle")}</span>
        </div>
      </div>
    </div>,
    document.body
  );
}
