import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { formatMoney, formatQuantity } from "../utils/format";

/** Line items + totals for an invoice or quote, read-only. */
export function LineItems({ document }) {
  const { t } = useTranslation();
  return (
    <section className="card overflow-hidden">
      <h2 className="border-b border-zinc-100 px-5 py-3.5 text-sm font-semibold text-zinc-900">{t("document.lineItems")}</h2>
      <ul className="divide-y divide-zinc-100">
        {document.items.map((item) => (
          <li key={item.id} className="flex items-start justify-between gap-4 px-5 py-4">
            <div className="min-w-0">
              <p className="text-zinc-900">{item.description}</p>
              <p className="text-sm tabular-nums text-zinc-500">
                {formatQuantity(item.quantity)} × {formatMoney(item.unit_price)}
                {Number(item.tax_rate) > 0 && ` · ${t("document.taxRate", { rate: Number(item.tax_rate) })}`}
              </p>
            </div>
            <span className="shrink-0 tabular-nums text-zinc-900">{formatMoney(item.line_total)}</span>
          </li>
        ))}
      </ul>
      <dl className="space-y-1.5 border-t border-zinc-200/80 bg-zinc-50/60 px-5 py-4 text-sm">
        <div className="flex justify-between text-zinc-600">
          <dt>{t("document.totalExcl")}</dt>
          <dd className="tabular-nums">{formatMoney(document.subtotal)}</dd>
        </div>
        <div className="flex justify-between text-zinc-600">
          <dt>{t("document.vat")}</dt>
          <dd className="tabular-nums">{formatMoney(document.tax_total)}</dd>
        </div>
        <div className="flex justify-between pt-1 text-base font-semibold text-zinc-900">
          <dt>{t("document.totalIncl")}</dt>
          <dd className="tabular-nums">{formatMoney(document.total)}</dd>
        </div>
      </dl>
    </section>
  );
}

export function DetailGrid({ rows }) {
  return (
    <dl className="card grid grid-cols-2 gap-x-4 gap-y-3 p-4 text-sm sm:grid-cols-4">
      {rows.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-zinc-500">{label}</dt>
          <dd className="mt-0.5 truncate font-medium text-zinc-900">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Side-panel summary: label/value rows, the last one emphasized. */
/** Who made a document and when, for its page (never printed). */
export function createdRow(t, doc, team, formatDate) {
  const who = team.get(doc.created_by)?.full_name;
  return [t("document.createdBy"), who ? `${who} · ${formatDate(doc.created_at)}` : formatDate(doc.created_at)];
}

export function SummaryCard({ title, rows, emphasis }) {
  const { t } = useTranslation();
  return (
    <section className="card p-5">
      <h2 className="mb-4 text-sm font-semibold text-zinc-900">{title ?? t("document.summary")}</h2>
      <dl className="space-y-3 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-4">
            <dt className="text-zinc-500">{label}</dt>
            <dd className="text-right font-medium text-zinc-900">{value}</dd>
          </div>
        ))}
      </dl>
      {emphasis && (
        <div className="mt-4 flex items-baseline justify-between gap-4 border-t border-zinc-100 pt-4">
          <span className="text-sm font-medium text-zinc-900">{emphasis[0]}</span>
          <span className="text-xl font-semibold tracking-tight text-zinc-900">{emphasis[1]}</span>
        </div>
      )}
    </section>
  );
}

export function BackLink({ to, children }) {
  return (
    <Link to={to} className="inline-flex items-center gap-1 text-sm font-medium text-zinc-500 transition-colors duration-150 hover:text-zinc-900">
      <svg viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4" aria-hidden="true">
        <path fillRule="evenodd" d="M9.78 4.22a.75.75 0 0 1 0 1.06L7.06 8l2.72 2.72a.75.75 0 1 1-1.06 1.06L5.47 8.53a.75.75 0 0 1 0-1.06l3.25-3.25a.75.75 0 0 1 1.06 0Z" clipRule="evenodd" />
      </svg>
      {children}
    </Link>
  );
}
