import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAgedReceivables } from "../hooks/useApi";
import { BackLink } from "../components/DocumentView";
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from "../components/ui";
import { formatDate, formatMoney } from "../utils/format";

// Oldest last; the colour deepens with how late the money is.
const BUCKETS = [
  { key: "current", label: "aging.current", tone: "bg-zinc-300", text: "text-zinc-900" },
  { key: "days_1_30", label: "aging.days1", tone: "bg-amber-300", text: "text-zinc-900" },
  { key: "days_31_60", label: "aging.days31", tone: "bg-orange-400", text: "text-zinc-900" },
  { key: "days_61_90", label: "aging.days61", tone: "bg-red-400", text: "text-red-700" },
  { key: "days_90_plus", label: "aging.days90", tone: "bg-red-600", text: "text-red-700" },
];

// A spreadsheet runs cells that start with = + - @ as formulas; quote them.
function csvCell(value) {
  let text = String(value ?? "");
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadCsv(report, t) {
  const header = [t("aging.customer"), ...BUCKETS.map((b) => t(b.label)), t("aging.total")];
  const rows = report.customers.map((c) => [c.customer_name, ...BUCKETS.map((b) => c[b.key]), c.total]);
  rows.push([t("aging.total"), ...BUCKETS.map((b) => report.totals[b.key]), report.totals.total]);
  const csv = [header, ...rows].map((r) => r.map(csvCell).join(",")).join("\r\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  link.download = `who-owes-you-${report.as_of}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

/** Who owes you: everything still owed on sent invoices, per customer, by
 *  how many days late it is. The customers to call first come first. */
export default function ReceivablesPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch } = useAgedReceivables();

  return (
    <>
      <PageHeader
        eyebrow={<BackLink to="/invoices">{t("nav.invoices")}</BackLink>}
        title={t("aging.title")}
        subtitle={data ? t("aging.subtitle", { date: formatDate(data.as_of) }) : undefined}
        actions={
          data?.customers.length ? (
            <button type="button" className="btn btn-secondary" onClick={() => downloadCsv(data, t)}>
              {t("aging.download")}
            </button>
          ) : null
        }
      />

      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : !data.customers.length ? (
        <EmptyState title={t("aging.empty")} description={t("aging.emptyHint")} />
      ) : (
        <>
          <dl className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {BUCKETS.map((b) => (
              <div key={b.key} className="card p-4">
                <dt className="flex items-center gap-2 text-xs font-medium text-zinc-500">
                  <span className={`h-2 w-2 rounded-full ${b.tone}`} aria-hidden="true" />
                  {t(b.label)}
                </dt>
                <dd className={`mt-1 text-lg font-semibold tabular-nums ${Number(data.totals[b.key]) > 0 ? b.text : "text-zinc-400"}`}>
                  {formatMoney(data.totals[b.key])}
                </dd>
              </div>
            ))}
            <div className="card col-span-2 bg-zinc-950 p-4 sm:col-span-1">
              <dt className="text-xs font-medium text-zinc-400">{t("aging.total")}</dt>
              <dd className="mt-1 text-lg font-semibold tabular-nums text-white">{formatMoney(data.totals.total)}</dd>
            </div>
          </dl>

          {/* Laptop: one row per customer, a column per age. */}
          <div className="card hidden overflow-x-auto md:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-100 text-left text-xs text-zinc-500">
                  <th className="px-4 py-3 font-medium">{t("aging.customer")}</th>
                  {BUCKETS.map((b) => (
                    <th key={b.key} className="px-4 py-3 text-right font-medium">
                      {t(b.label)}
                    </th>
                  ))}
                  <th className="px-4 py-3 text-right font-medium">{t("aging.total")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {data.customers.map((c) => (
                  <tr key={c.customer_id} className="hover:bg-zinc-50">
                    <td className="px-4 py-3">
                      <Link to={`/customers/${c.customer_id}/statement`} className="font-medium text-zinc-900 hover:underline">
                        {c.customer_name}
                      </Link>
                      <p className="text-xs text-zinc-500">{t("aging.invoices", { count: c.invoices })}</p>
                    </td>
                    {BUCKETS.map((b) => (
                      <td key={b.key} className={`px-4 py-3 text-right tabular-nums ${Number(c[b.key]) > 0 ? b.text : "text-zinc-300"}`}>
                        {Number(c[b.key]) > 0 ? formatMoney(c[b.key]) : "—"}
                      </td>
                    ))}
                    <td className="px-4 py-3 text-right font-semibold tabular-nums text-zinc-900">{formatMoney(c.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Phone: a card per customer, with a bar of how late the money is. */}
          <ul className="space-y-3 md:hidden">
            {data.customers.map((c) => (
              <li key={c.customer_id}>
                <Link to={`/customers/${c.customer_id}/statement`} className="card block p-4 active:bg-zinc-50">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="min-w-0 truncate font-medium text-zinc-900">{c.customer_name}</span>
                    <span className="shrink-0 font-semibold tabular-nums text-zinc-900">{formatMoney(c.total)}</span>
                  </div>
                  <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-zinc-100" aria-hidden="true">
                    {BUCKETS.map((b) => (
                      <span key={b.key} className={b.tone} style={{ width: `${(Number(c[b.key]) / Number(c.total)) * 100}%` }} />
                    ))}
                  </div>
                  <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-zinc-600">
                    {BUCKETS.filter((b) => Number(c[b.key]) > 0).map((b) => (
                      <li key={b.key} className="inline-flex items-center gap-1.5">
                        <span className={`h-1.5 w-1.5 rounded-full ${b.tone}`} aria-hidden="true" />
                        {t(b.label)}: <span className="tabular-nums">{formatMoney(c[b.key])}</span>
                      </li>
                    ))}
                  </ul>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
