import { useDeferredValue, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { useTour } from "../components/Tour";
import { APP_NAME } from "../components/Brand";
import { PageHeader, SearchInput } from "../components/ui";

// The same sections the tour walks through, each with where it lives.
const SECTIONS = [
  { key: "dashboard", to: "/" },
  { key: "getStarted", to: "/" },
  { key: "activities", to: "/activities" },
  { key: "messages", to: "/messages" },
  { key: "deals", to: "/deals" },
  { key: "quotes", to: "/quotes" },
  { key: "invoices", to: "/invoices" },
  { key: "purchaseOrders", to: "/purchase-orders" },
  { key: "marketing", to: "/marketing" },
  { key: "customers", to: "/customers" },
  { key: "products", to: "/products" },
  { key: "search" },
  { key: "settings", to: "/settings", admin: true },
  { key: "language" },
  { key: "about", to: "/about" },
];
const PARTS = ["p1", "p2", "p3", "p4"];
const HOWTOS = ["1", "2"];
const SHORTCUTS = [
  ["Ctrl K", "help.shortcuts.search"],
  ["Ctrl Enter", "help.shortcuts.send"],
  ["Enter", "help.shortcuts.chat"],
  ["Esc", "help.shortcuts.close"],
];

export default function HelpPage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const { start } = useTour();
  const [query, setQuery] = useState("");
  const q = useDeferredValue(query).trim().toLowerCase();
  const isAdmin = user?.role === "admin";

  const sections = SECTIONS.filter((s) => !s.admin || isAdmin).map((s) => {
    const base = `help.sections.${s.key}`;
    const parts = PARTS.filter((p) => i18n.exists(`${base}.${p}`)).map((p) => t(`${base}.${p}`));
    const howtos = HOWTOS.filter((n) => i18n.exists(`${base}.q${n}`)).map((n) => ({ q: t(`${base}.q${n}`), a: t(`${base}.a${n}`) }));
    const text = [t(`${base}.title`), t(`${base}.summary`), ...parts, ...howtos.flatMap((h) => [h.q, h.a])].join(" ").toLowerCase();
    return { ...s, base, parts, howtos, match: !q || text.includes(q) };
  });
  const shown = sections.filter((s) => s.match);

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("help.title")}
        subtitle={t("help.subtitle", { app: APP_NAME })}
        actions={
          <button type="button" className="btn btn-primary" onClick={start}>
            {t("help.takeTour")}
          </button>
        }
      />
      <SearchInput value={query} onChange={setQuery} placeholder={t("help.search")} />

      {!q && (
        <nav className="flex flex-wrap gap-2" aria-label={t("help.jumpTo")}>
          {sections.map((s) => (
            <a key={s.key} href={`#help-${s.key}`} className="rounded-full bg-white px-3 py-1 text-[13px] font-medium text-zinc-600 ring-1 ring-zinc-200 hover:text-zinc-900">
              {t(`${s.base}.title`)}
            </a>
          ))}
        </nav>
      )}

      {shown.length === 0 ? (
        <p className="card px-5 py-10 text-center text-sm text-zinc-500">{t("help.noResults", { query })}</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {shown.map((s) => (
            <section key={s.key} id={`help-${s.key}`} className="card scroll-mt-6 p-5">
              <div className="flex items-start justify-between gap-3">
                <h2 className="font-semibold text-zinc-900">{t(`${s.base}.title`)}</h2>
                {s.to && (
                  <Link to={s.to} className="shrink-0 text-[13px] font-medium text-indigo-600 hover:text-indigo-700">
                    {t("help.open")} →
                  </Link>
                )}
              </div>
              <p className="mt-1 text-sm leading-relaxed text-zinc-600">{t(`${s.base}.summary`)}</p>
              {s.parts.length > 0 && (
                <>
                  <p className="mb-1.5 mt-3 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{t("tour.whatsHere")}</p>
                  <ul className="space-y-1 text-[13px] text-zinc-700">
                    {s.parts.map((part) => (
                      <li key={part} className="flex gap-2">
                        <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-indigo-500" aria-hidden="true" />
                        {part}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {s.howtos.length > 0 && (
                <div className="mt-3 divide-y divide-zinc-100 border-t border-zinc-100">
                  {s.howtos.map((h) => (
                    <details key={h.q} className="group py-2" open={Boolean(q)}>
                      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm font-medium text-zinc-800">
                        {h.q}
                        <span className="text-zinc-400 transition-transform duration-150 group-open:rotate-90" aria-hidden="true">
                          ›
                        </span>
                      </summary>
                      <p className="mt-1.5 text-sm leading-relaxed text-zinc-600">{h.a}</p>
                    </details>
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      )}

      <section className="card p-5">
        <h2 className="font-semibold text-zinc-900">{t("help.shortcutsTitle")}</h2>
        <dl className="mt-3 grid gap-2 sm:grid-cols-2">
          {SHORTCUTS.map(([keys, label]) => (
            <div key={keys} className="flex items-center justify-between gap-3 rounded-lg bg-zinc-50 px-3 py-2 text-sm">
              <dt className="text-zinc-600">{t(label)}</dt>
              <dd>
                <kbd className="rounded-md bg-white px-2 py-0.5 font-mono text-xs text-zinc-700 ring-1 ring-zinc-200">{keys}</kbd>
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-sm text-zinc-500">{t("help.stillStuck")}</p>
      </section>
    </div>
  );
}
