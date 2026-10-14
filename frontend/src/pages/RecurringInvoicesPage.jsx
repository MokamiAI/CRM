import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useCustomerMap } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import DocumentEditor from "../components/DocumentEditor";
import { BackLink } from "../components/DocumentView";
import Sheet from "../components/Sheet";
import { PlanNotice, useHasFeature } from "../components/Billing";
import { Button, ButtonLink, EmptyState, ErrorState, Field, ListSkeleton, PageHeader, PlusIcon, StatusBadge } from "../components/ui";
import { errorMessage, formatDate, formatMoney } from "../utils/format";

const FREQUENCIES = ["weekly", "monthly", "quarterly", "yearly"];
const get = (path) => apiClient.get(path).then((r) => r.data);

function useRecurringList() {
  return useQuery({ queryKey: ["recurring"], queryFn: () => get("/recurring-invoices") });
}

function ActiveBadge({ active }) {
  const { t } = useTranslation();
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${active ? "bg-emerald-50 text-emerald-700 ring-emerald-200/70" : "bg-zinc-100 text-zinc-600 ring-zinc-200"}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-emerald-500" : "bg-zinc-400"}`} aria-hidden="true" />
      {t(active ? "recurring.active" : "recurring.paused")}
    </span>
  );
}

/** Retainers and contracts: each cycle makes a draft invoice to check and send. */
export function RecurringInvoicesPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data, isLoading, isError, refetch } = useRecurringList();
  const customers = useCustomerMap();
  const included = useHasFeature("recurring_invoices");
  const canWrite = user?.role !== "viewer" && included !== false;
  const newButton = canWrite && (
    <ButtonLink to="/invoices/recurring/new">
      <PlusIcon className="h-4 w-4" /> {t("recurring.new")}
    </ButtonLink>
  );

  return (
    <>
      <PageHeader eyebrow={<BackLink to="/invoices">{t("nav.invoices")}</BackLink>} title={t("recurring.title")} subtitle={t("recurring.subtitle")} actions={newButton} />
      {included === false && (
        <div className="mb-5">
          <PlanNotice feature="recurring_invoices" />
        </div>
      )}
      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : data.length === 0 ? (
        included !== false && <EmptyState title={t("recurring.empty")} description={t("recurring.emptyHint")} action={newButton} />
      ) : (
        <ul className="card divide-y divide-zinc-100">
          {data.map((s) => (
            <li key={s.id}>
              <Link to={`/invoices/recurring/${s.id}`} className="flex items-center gap-4 px-4 py-3.5 hover:bg-zinc-50">
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium text-zinc-900">{customers.get(s.customer_id)?.name ?? "…"}</span>
                    <ActiveBadge active={s.active} />
                  </span>
                  <span className="mt-0.5 block text-xs text-zinc-500">
                    {t(`recurring.every.${s.frequency}`)}
                    {s.reference && ` · ${s.reference}`}
                    {s.active && ` · ${t("recurring.nextOn", { date: formatDate(s.next_run_date) })}`}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block font-semibold tabular-nums text-zinc-900">{formatMoney(s.total)}</span>
                  <span className="text-xs text-zinc-500">{t("recurring.perInvoice")}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function NewRecurringInvoicePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [frequency, setFrequency] = useState("monthly");
  const [endDate, setEndDate] = useState("");
  const [dueDays, setDueDays] = useState("");
  const included = useHasFeature("recurring_invoices");

  const create = useMutation({
    mutationFn: (payload) => apiClient.post("/recurring-invoices", payload).then((r) => r.data),
    onSuccess: (schedule) => {
      queryClient.invalidateQueries({ queryKey: ["recurring"] });
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      toast.success(t("recurring.saved"));
      navigate(`/invoices/recurring/${schedule.id}`, { replace: true });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <div>
      <PageHeader eyebrow={<BackLink to="/invoices/recurring">{t("recurring.title")}</BackLink>} title={t("recurring.new")} subtitle={t("recurring.newHint")} />
      {included === false ? (
        <PlanNotice feature="recurring_invoices" />
      ) : (
        <DocumentEditor
        issueLabel={t("recurring.firstOn")}
        submitLabel={t("recurring.save")}
        isSubmitting={create.isPending}
        onSubmit={({ issue_date, customer_id, reference, notes, items }) =>
          create.mutate({
            customer_id,
            frequency,
            start_date: issue_date,
            end_date: endDate || null,
            due_days: dueDays === "" ? null : Number(dueDays),
            reference,
            notes,
            items,
          })
        }
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label={t("recurring.frequency")}>
            <select className="input" value={frequency} onChange={(e) => setFrequency(e.target.value)}>
              {FREQUENCIES.map((f) => (
                <option key={f} value={f}>
                  {t(`recurring.every.${f}`)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("recurring.endsOn")} hint={t("recurring.endsHint")}>
            <input className="input" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </Field>
          <Field label={t("recurring.dueDays")} hint={t("recurring.dueDaysHint")}>
            <input className="input" type="number" min="0" max="365" inputMode="numeric" value={dueDays} onChange={(e) => setDueDays(e.target.value)} />
          </Field>
        </div>
        </DocumentEditor>
      )}
    </div>
  );
}

export function RecurringInvoiceDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const customers = useCustomerMap();
  const [confirming, setConfirming] = useState(false);
  const { data: s, isLoading, isError, refetch } = useQuery({ queryKey: ["recurring", id], queryFn: () => get(`/recurring-invoices/${id}`) });
  const canWrite = user?.role !== "viewer";
  const canManage = ["admin", "manager"].includes(user?.role);
  const included = useHasFeature("recurring_invoices");
  const onError = (error) => toast.error(errorMessage(error));
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["recurring"] });

  const toggle = useMutation({
    mutationFn: () => apiClient.post(`/recurring-invoices/${id}/${s.active ? "pause" : "resume"}`),
    onSuccess: () => refresh(),
    onError,
  });
  const remove = useMutation({
    mutationFn: () => apiClient.delete(`/recurring-invoices/${id}`),
    onSuccess: () => {
      refresh();
      toast.success(t("recurring.deleted"));
      navigate("/invoices/recurring", { replace: true });
    },
    onError,
  });

  if (isLoading) return <ListSkeleton />;
  if (isError) return <ErrorState onRetry={refetch} />;
  const customer = customers.get(s.customer_id);
  const rows = [
    [t("recurring.frequency"), t(`recurring.every.${s.frequency}`)],
    [t("recurring.perInvoice"), formatMoney(s.total)],
    [t("recurring.next"), s.active ? formatDate(s.next_run_date) : "—"],
    [t("recurring.endsOn"), s.end_date ? formatDate(s.end_date) : t("recurring.noEnd")],
    [t("recurring.dueDays"), s.due_days ?? t("recurring.usualTerms")],
    ...(s.reference ? [[t("editor.reference"), s.reference]] : []),
  ];

  return (
    <>
      <PageHeader
        eyebrow={<BackLink to="/invoices/recurring">{t("recurring.title")}</BackLink>}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {customer ? <Link to={`/customers/${customer.id}`} className="hover:underline">{customer.name}</Link> : "…"} <ActiveBadge active={s.active} />
          </span>
        }
        subtitle={t("recurring.detailHint")}
        actions={
          canWrite && (
            <>
              {canManage && (
                <Button variant="danger" onClick={() => setConfirming(true)}>
                  {t("recurring.delete")}
                </Button>
              )}
              {(s.active || included !== false) && (
                <Button variant={s.active ? "secondary" : "primary"} disabled={toggle.isPending} onClick={() => toggle.mutate()}>
                  {t(s.active ? "recurring.pause" : "recurring.resume")}
                </Button>
              )}
            </>
          )
        }
      />
      {included === false && (
        <div className="mb-5">
          <PlanNotice feature="recurring_invoices" />
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <section className="card p-5">
          <dl className="space-y-3 text-sm">
            {rows.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4">
                <dt className="text-zinc-500">{label}</dt>
                <dd className="text-right font-medium text-zinc-900">{value}</dd>
              </div>
            ))}
          </dl>
          <ul className="mt-5 space-y-1.5 border-t border-zinc-100 pt-4 text-sm">
            {s.items.map((item, i) => (
              <li key={i} className="flex justify-between gap-4">
                <span className="min-w-0 truncate text-zinc-700">
                  {Number(item.quantity)} × {item.description}
                </span>
                <span className="shrink-0 tabular-nums text-zinc-500">{formatMoney(Number(item.quantity) * Number(item.unit_price))}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h2 className="border-b border-zinc-100 px-5 py-3.5 text-sm font-semibold text-zinc-900">{t("recurring.made")}</h2>
          {s.invoices.length === 0 ? (
            <p className="px-5 py-4 text-sm text-zinc-500">{t("recurring.noneMade")}</p>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {s.invoices.map((inv) => (
                <li key={inv.id}>
                  <Link to={`/invoices/${inv.id}`} className="flex items-center justify-between gap-3 px-5 py-3 text-sm hover:bg-zinc-50">
                    <span className="flex items-center gap-3">
                      <span className="font-medium text-zinc-900">{inv.invoice_number}</span>
                      <StatusBadge status={inv.status} />
                    </span>
                    <span className="flex items-center gap-4 text-zinc-500">
                      <span>{formatDate(inv.issue_date)}</span>
                      <span className="tabular-nums text-zinc-900">{formatMoney(inv.total)}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <Sheet
        open={confirming}
        onClose={() => setConfirming(false)}
        title={t("recurring.delete")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
              {t("recurring.delete")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-zinc-600">{t("recurring.deleteConfirm")}</p>
      </Sheet>
    </>
  );
}
