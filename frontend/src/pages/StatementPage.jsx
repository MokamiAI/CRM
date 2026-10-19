import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { useCustomer } from "../hooks/useApi";
import { BackLink } from "../components/DocumentView";
import { DocumentViewer } from "../components/Documents";
import { Button, ErrorState, FilterChips, ListSkeleton, PageHeader } from "../components/ui";
import { errorMessage, formatDate, formatMoney } from "../utils/format";

const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** Date ranges people ask for most; "custom" keeps whatever was typed. */
function presetRange(preset) {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  switch (preset) {
    case "thisMonth":
      return [iso(new Date(y, m, 1)), iso(now)];
    case "last3":
      return [iso(new Date(y, m - 2, 1)), iso(now)];
    case "thisYear":
      return [iso(new Date(y, 0, 1)), iso(now)];
    case "lastYear":
      return [iso(new Date(y - 1, 0, 1)), iso(new Date(y - 1, 11, 31))];
    default:
      return null;
  }
}
const PRESETS = ["thisMonth", "last3", "thisYear", "lastYear", "custom"];

/** A client's statement: what they owed going in, every invoice and
 *  payment in the period, what they owe now and how overdue it is. */
export default function StatementPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const { user } = useAuth();
  const { data: customer } = useCustomer(id);
  const [params, setParams] = useSearchParams();
  const preset = PRESETS.includes(params.get("period")) ? params.get("period") : "last3";
  const [start, end] = presetRange(preset) ?? [params.get("from") || presetRange("last3")[0], params.get("to") || iso(new Date())];
  const [viewing, setViewing] = useState(false);
  const query = useMemo(() => new URLSearchParams({ start, end }).toString(), [start, end]);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["statement", id, start, end],
    queryFn: () => apiClient.get(`/customers/${id}/statement?${query}`).then((r) => r.data),
    enabled: start <= end,
  });
  const send = useMutation({
    mutationFn: () => apiClient.post(`/customers/${id}/statement/send`, { start, end }).then((r) => r.data),
    onSuccess: (r) => toast.success(t("statement.sent", { email: r.sent_to })),
    onError: (error) => toast.error(errorMessage(error, t("statement.sendFailed"))),
  });

  const setPreset = (value) => setParams(value === "custom" ? { period: "custom", from: start, to: end } : { period: value }, { replace: true });
  const setDate = (field) => (e) => setParams({ period: "custom", from: field === "from" ? e.target.value : start, to: field === "to" ? e.target.value : end }, { replace: true });
  const canSend = user?.role !== "viewer";
  const ageing = data?.ageing;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<BackLink to={`/customers/${id}`}>{customer?.name ?? t("nav.customers")}</BackLink>}
        title={t("statement.title")}
        subtitle={customer?.name}
        actions={
          <>
            <Button variant="secondary" onClick={() => setViewing(true)} disabled={!data}>
              {t("documents.print")}
            </Button>
            {canSend && (
              <Button onClick={() => send.mutate()} disabled={!data || !customer?.recipient_email || send.isPending}>
                {send.isPending ? t("common.sending") : t("statement.email")}
              </Button>
            )}
          </>
        }
      />
      {customer && !customer.recipient_email && canSend && <p className="-mt-2 text-sm text-zinc-500">{t("statement.noEmail")}</p>}

      <section className="card space-y-3 p-4">
        <FilterChips value={preset} onChange={setPreset} options={PRESETS.map((p) => ({ value: p, label: t(`statement.presets.${p}`) }))} />
        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="label">{t("statement.from")}</span>
            <input type="date" className="input" value={start} max={end} onChange={setDate("from")} />
          </label>
          <label className="block">
            <span className="label">{t("statement.to")}</span>
            <input type="date" className="input" value={end} min={start} onChange={setDate("to")} />
          </label>
        </div>
      </section>

      {isLoading ? (
        <ListSkeleton rows={4} />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : data ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ["opening", data.opening_balance],
              ["invoiced", data.invoiced],
              ["paid", data.paid],
              ["closing", data.closing_balance],
            ].map(([key, value]) => (
              <div key={key} className={`card p-4 ${key === "closing" ? "ring-2 ring-indigo-500/60" : ""}`}>
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{t(`statement.${key}`)}</p>
                <p className="mt-1 text-xl font-semibold tabular-nums tracking-tight text-zinc-900">{formatMoney(value)}</p>
              </div>
            ))}
          </div>

          <section className="card p-4 sm:p-5">
            <h2 className="mb-3 text-sm font-semibold text-zinc-900">{t("statement.ageing")}</h2>
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
              {[
                ["current", ageing.current],
                ["d30", ageing.days_30],
                ["d60", ageing.days_60],
                ["d90", ageing.days_90],
                ["d120", ageing.days_120],
              ].map(([key, value]) => (
                <div key={key} className="rounded-lg bg-zinc-50 px-3 py-2">
                  <dt className="text-xs text-zinc-500">{t(`statement.${key}`)}</dt>
                  <dd className={`font-medium tabular-nums ${key !== "current" && value > 0 ? "text-rose-600" : "text-zinc-900"}`}>{formatMoney(value)}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead className="table-head">
                <tr>
                  <th>{t("statement.col.date")}</th>
                  <th>{t("statement.col.details")}</th>
                  <th className="hidden text-right sm:table-cell">{t("statement.col.debit")}</th>
                  <th className="hidden text-right sm:table-cell">{t("statement.col.credit")}</th>
                  <th className="text-right">{t("statement.col.balance")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                <tr>
                  <td className="whitespace-nowrap px-4 py-3 text-zinc-500">{formatDate(start)}</td>
                  <td className="px-4 py-3 text-zinc-500">{t("statement.opening")}</td>
                  <td className="hidden sm:table-cell" />
                  <td className="hidden sm:table-cell" />
                  <td className="px-4 py-3 text-right tabular-nums">{formatMoney(data.opening_balance)}</td>
                </tr>
                {data.lines.map((line, i) => (
                  <tr key={i}>
                    <td className="whitespace-nowrap px-4 py-3 text-zinc-500">{formatDate(line.date)}</td>
                    <td className="px-4 py-3">
                      <span className="font-medium text-zinc-900">{line.reference}</span>{" "}
                      <span className="text-zinc-500">· {line.kind === "invoice" ? t("statement.invoice") : line.description}</span>
                      <span className={`block tabular-nums sm:hidden ${line.debit ? "text-zinc-700" : "text-emerald-700"}`}>
                        {line.debit ? formatMoney(line.debit) : `− ${formatMoney(line.credit)}`}
                      </span>
                    </td>
                    <td className="hidden px-4 py-3 text-right tabular-nums sm:table-cell">{line.debit ? formatMoney(line.debit) : ""}</td>
                    <td className="hidden px-4 py-3 text-right tabular-nums text-emerald-700 sm:table-cell">{line.credit ? formatMoney(line.credit) : ""}</td>
                    <td className="px-4 py-3 text-right font-medium tabular-nums text-zinc-900">{formatMoney(line.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.lines.length === 0 && <p className="border-t border-zinc-100 px-4 py-6 text-center text-sm text-zinc-500">{t("statement.empty")}</p>}
          </section>
        </>
      ) : null}

      <DocumentViewer
        open={viewing}
        onClose={() => setViewing(false)}
        url={`/customers/${id}/statement/document?${query}`}
        title={`${t("statement.title")} · ${customer?.name ?? ""}`}
      />
    </div>
  );
}
