import { KpiCard, StatStrip } from "../components/dashboard";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import apiClient from "../services/apiClient";
import { useCustomerMap, useQuote, useQuotes, useTeamMap } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import DocumentEditor from "../components/DocumentEditor";
import { RowEditButton } from "../components/crm";
import { BackLink, LineItems, SummaryCard, createdRow } from "../components/DocumentView";
import Sheet from "../components/Sheet";
import { ClientFilter, DocumentViewer } from "../components/Documents";
import {
  Button,
  ButtonLink,
  EmptyState,
  ErrorState,
  FilterChips,
  ListSkeleton,
  Avatar,
  PageHeader,
  PlusIcon,
  StatusBadge,
} from "../components/ui";
import { errorMessage, formatDate, formatMoney, formatMoneyWhole, formatShortDate, todayISO } from "../utils/format";
import ImportExportButtons from "../components/ImportExport";

const STATUS_FILTERS = [
  { value: "", key: "common.all" },
  { value: "draft", key: "status.draft" },
  { value: "sent", key: "status.sent" },
  { value: "accepted", key: "status.accepted" },
  { value: "converted", key: "status.converted" },
  { value: "rejected", key: "status.rejected" },
  { value: "expired", key: "status.expired" },
];

export function QuotesPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [status, setStatus] = useState("");
  const [params, setParams] = useSearchParams();
  const client = params.get("client") ?? "";
  const setClient = (id) => setParams(id ? { client: id } : {}, { replace: true });
  const { data, isLoading, isError, refetch } = useQuotes({ ...(status ? { status } : {}), ...(client ? { customer_id: client } : {}) });
  const customers = useCustomerMap();
  const { data: sent = [] } = useQuotes({ status: "sent" });
  const { data: drafts = [] } = useQuotes({ status: "draft" });
  // Won: accepted, or already turned into an invoice (accepting does that).
  const { data: acceptedOnly = [] } = useQuotes({ status: "accepted" });
  const { data: converted = [] } = useQuotes({ status: "converted" });
  const accepted = [...acceptedOnly, ...converted];
  const weekAhead = new Date(`${todayISO()}T00:00:00`);
  weekAhead.setDate(weekAhead.getDate() + 7);
  const expiring = sent.filter((q) => q.expiry_date && q.expiry_date <= weekAhead.toISOString().slice(0, 10));
  const worth = (list) => list.reduce((n, q) => n + Number(q.total), 0);

  return (
    <>
      <PageHeader
        title={t("nav.quotes")}
        subtitle={data ? t(status ? "quotes.count" : "quotes.countTotal", { count: data.length }) : undefined}
        actions={
          <>
            <ImportExportButtons entity="quotes" />
            {user?.role !== "viewer" && (
              <ButtonLink to="/quotes/new">
                <PlusIcon className="h-4 w-4" /> {t("quotes.new")}
              </ButtonLink>
            )}
          </>
        }
      />
      <StatStrip>
        <KpiCard compact icon="quote" tone="blue" label={t("dashboard.awaitingReply")} value={formatMoneyWhole(worth(sent))} detail={t("lists.quotes", { count: sent.length })} />
        <KpiCard compact icon="activity" tone="amber" label={t("lists.expiring")} value={expiring.length} detail={formatMoneyWhole(worth(expiring))} />
        <KpiCard compact icon="quote" tone="violet" label={t("lists.drafts")} value={drafts.length} detail={t("lists.notSent", { count: drafts.length })} />
        <KpiCard compact icon="cash" tone="emerald" label={t("status.accepted")} value={formatMoneyWhole(worth(accepted))} detail={t("lists.quotes", { count: accepted.length })} />
      </StatStrip>
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1 sm:max-w-sm">
          <ClientFilter value={client} onChange={setClient} />
        </div>
        {client && (
          <ButtonLink variant="secondary" to={`/customers/${client}/statement`}>
            {t("statement.get")}
          </ButtonLink>
        )}
      </div>
      <FilterChips options={STATUS_FILTERS.map((o) => ({ ...o, label: t(o.key) }))} value={status} onChange={setStatus} />

      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : data.length === 0 ? (
        <EmptyState
          title={t(status || client ? "quotes.noneWithStatus" : "quotes.none")}
          description={status ? undefined : t("quotes.noneHint")}
        />
      ) : (
        <QuoteList quotes={data} customers={customers} />
      )}
    </>
  );
}

// Where a row's pencil goes: a draft opens the editor; a sent quote opens
// its page, which asks before turning it back into a draft.
const EDITABLE_QUOTE = {
  draft: (id) => `/quotes/${id}/edit`,
  sent: (id) => `/quotes/${id}?edit=1`,
  expired: (id) => `/quotes/${id}?edit=1`,
};

function QuoteList({ quotes, customers }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const nameOf = (quote) => customers.get(quote.customer_id)?.name ?? "…";
  return (
    <div className="card overflow-hidden">
      <table className="hidden w-full md:table">
        <thead className="table-head">
          <tr>
            <th>{t("palette.kind.quote")}</th>
            <th>{t("invoices.col.customer")}</th>
            <th>{t("invoices.col.issued")}</th>
            <th>{t("quotes.validUntil")}</th>
            <th>{t("invoices.col.status")}</th>
            <th className="text-right">{t("invoices.col.amount")}</th>
            <th className="w-12"><span className="sr-only">{t("common.edit")}</span></th>
          </tr>
        </thead>
        <tbody>
          {quotes.map((quote) => (
            <tr key={quote.id} className="table-row" onClick={() => navigate(`/quotes/${quote.id}`)}>
              <td className="whitespace-nowrap font-medium text-zinc-900">
                <Link to={`/quotes/${quote.id}`} onClick={(e) => e.stopPropagation()} className="hover:underline">
                  {quote.quote_number}
                </Link>
              </td>
              <td>
                <div className="flex items-center gap-2.5">
                  <Avatar name={nameOf(quote)} size="sm" />
                  <span className="min-w-0">
                    <span className="block truncate text-zinc-700">{nameOf(quote)}</span>
                    {quote.title && <span className="block truncate text-xs text-zinc-500">{quote.title}</span>}
                  </span>
                </div>
              </td>
              <td className="whitespace-nowrap text-zinc-500">{formatShortDate(quote.issue_date)}</td>
              <td className="whitespace-nowrap text-zinc-500">{quote.expiry_date ? formatShortDate(quote.expiry_date) : "—"}</td>
              <td>
                <StatusBadge status={quote.status} />
              </td>
              <td className="whitespace-nowrap text-right font-medium tabular-nums text-zinc-900">{formatMoney(quote.total)}</td>
              <td className="text-right">
                {canWrite && EDITABLE_QUOTE[quote.status] && <RowEditButton label={t("edit.title", { number: quote.quote_number })} to={EDITABLE_QUOTE[quote.status](quote.id)} />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="divide-y divide-zinc-100 md:hidden">
        {quotes.map((quote) => (
          <li key={quote.id}>
            <Link to={`/quotes/${quote.id}`} className="flex items-center gap-3 px-4 py-3.5 transition-colors duration-150 active:bg-zinc-50">
              <Avatar name={nameOf(quote)} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-zinc-900">{nameOf(quote)}</p>
                <p className="truncate text-[13px] text-zinc-500">
                  {quote.quote_number}
                  {quote.expiry_date && ` · ${t("quotes.validUntilDate", { date: formatShortDate(quote.expiry_date) })}`}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <p className="font-medium tabular-nums text-zinc-900">{formatMoney(quote.total)}</p>
                <StatusBadge status={quote.status} />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function NewQuotePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  // Opened from a customer or deal page: ?customer=…&deal=… pre-fill the
  // customer and link the quote to the deal.
  const [searchParams] = useSearchParams();
  const dealId = searchParams.get("deal");
  const queryClient = useQueryClient();
  const create = useMutation({
    mutationFn: (payload) => apiClient.post("/quotes", payload).then((res) => res.data),
    onSuccess: (quote) => {
      queryClient.invalidateQueries({ queryKey: ["quotes"] });
      queryClient.invalidateQueries({ queryKey: ["deal-quotes"] });
      for (const key of ["deal", "deals", "timeline", "reports"]) queryClient.invalidateQueries({ queryKey: [key] });
      toast.success(t("invoices.draftCreated", { number: quote.quote_number }));
      navigate(`/quotes/${quote.id}`, { replace: true });
    },
    onError: (error) => toast.error(errorMessage(error, t("quotes.createFailed"))),
  });

  return (
    <div className="max-w-3xl">
      <PageHeader eyebrow={<BackLink to="/quotes">{t("nav.quotes")}</BackLink>} title={t("quotes.new")} subtitle={t("invoices.draftNote")} />
      <DocumentEditor
        kind="quote"
        dateField="expiry_date"
        dateLabel={t("quotes.validUntil")}
        dateHint={t("quotes.optional")}
        submitLabel={t("invoices.saveDraft")}
        isSubmitting={create.isPending}
        initialCustomerId={searchParams.get("customer") ?? undefined}
        onSubmit={(payload) => create.mutate({ ...payload, deal_id: dealId })}
      />
    </div>
  );
}

// Outcome transitions available once a quote is sent (quote_service.py).
const OUTCOMES = [
  { action: "accept", variant: "primary" },
  { action: "reject", variant: "secondary" },
  { action: "expire", variant: "secondary" },
];

export function QuoteDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";

  const { data: quote, isLoading, isError, refetch } = useQuote(id);
  const customer = useCustomerMap().get(quote?.customer_id);
  const recipientEmail = quote?.recipient_email || customer?.recipient_email;
  const team = useTeamMap();
  const [sheet, setSheet] = useState(null);
  // A row's pencil on a sent quote arrives as ?edit=1: ask once.
  const [searchParams, setSearchParams] = useSearchParams();
  if (quote && searchParams.get("edit") && !sheet) {
    setSearchParams({}, { replace: true });
    if (canWrite && ["sent", "expired"].includes(quote.status)) setSheet("revise");
  }
  const [notify, setNotify] = useState(true);
  const close = () => setSheet(null);

  const queryClient = useQueryClient();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["deals"] });
    queryClient.invalidateQueries({ queryKey: ["pipeline-accounts"] });
    queryClient.invalidateQueries({ queryKey: ["customers"] });
    queryClient.invalidateQueries({ queryKey: ["deal-quotes"] });
    queryClient.invalidateQueries({ queryKey: ["quote", id] });
    queryClient.invalidateQueries({ queryKey: ["quotes"] });
  };
  const onError = (error) => toast.error(errorMessage(error));

  const send = useMutation({
    mutationFn: () => apiClient.post(`/quotes/${id}/send`, null, { params: { notify } }),
    onSuccess: () => {
      refresh();
      close();
      toast.success(t("quote.sent"), {
        description: notify && recipientEmail ? t("invoice.emailing", { email: recipientEmail }) : t("invoice.sentNoEmail"),
      });
    },
    onError,
  });

  const resend = useMutation({
    mutationFn: () => apiClient.post(`/quotes/${id}/resend`),
    onSuccess: () => toast.success(t("quote.resent"), { description: recipientEmail }),
    onError,
  });

  const transition = useMutation({
    mutationFn: (outcome) => apiClient.post(`/quotes/${id}/${outcome.action}`).then((res) => ({ outcome, quote: res.data })),
    onSuccess: ({ outcome, quote: updated }) => {
      refresh();
      // Accepting makes a draft invoice straight away (never sent by itself).
      if (updated?.invoice_id) {
        queryClient.invalidateQueries({ queryKey: ["invoices"] });
        toast.success(t("quote.acceptedDraft", { number: updated.invoice_number }), {
          action: { label: t("quote.reviewDraft"), onClick: () => navigate(`/invoices/${updated.invoice_id}`) },
        });
        return;
      }
      toast.success(i18n.t(`quote.done.${outcome.action}`));
    },
    onError,
  });

  const convert = useMutation({
    mutationFn: () => apiClient.post(`/invoices/from-quote/${id}`, {}).then((res) => res.data),
    onSuccess: (invoice) => {
      refresh();
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      toast.success(t("quote.converted", { number: invoice.invoice_number }));
      navigate(`/invoices/${invoice.id}`);
    },
    onError,
  });

  // Edit on a sent quote: back to draft first, then the editor.
  const revise = useMutation({
    mutationFn: () => apiClient.post(`/quotes/${id}/revise`),
    onSuccess: () => {
      refresh();
      close();
      navigate(`/quotes/${id}/edit`);
    },
    onError,
  });

  const remove = useMutation({
    mutationFn: () => apiClient.delete(`/quotes/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quotes"] });
      toast.success(t("invoice.draftDeleted"));
      navigate("/quotes", { replace: true });
    },
    onError,
  });

  if (isLoading) return <ListSkeleton rows={4} />;
  if (isError) return <ErrorState onRetry={refetch} />;

  const hasEmail = Boolean(recipientEmail);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={<BackLink to="/quotes">{t("nav.quotes")}</BackLink>}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {quote.quote_number} <StatusBadge status={quote.status} />
          </span>
        }
        subtitle={quote.title ? `${quote.title} · ${customer?.name ?? ""}` : customer?.name}
        actions={
          <>
            <Button variant="secondary" onClick={() => setSheet("view")}>
              {t("documents.view")}
            </Button>
            {canWrite && (
            <>
              {quote.status === "draft" && (
                <>
                  <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
                    {t("invoice.deleteDraft")}
                  </Button>
                  <ButtonLink variant="secondary" to={`/quotes/${id}/edit`}>
                    {t("common.edit")}
                  </ButtonLink>
                  <Button onClick={() => setSheet("send")}>{t("quote.send")}</Button>
                </>
              )}
              {["sent", "expired"].includes(quote.status) && (
                <Button variant="secondary" onClick={() => setSheet("revise")}>
                  {t("common.edit")}
                </Button>
              )}
              {["sent", "accepted"].includes(quote.status) && hasEmail && (
                <Button variant="secondary" disabled={resend.isPending} onClick={() => resend.mutate()}>
                  {resend.isPending ? t("common.sending") : t("quote.resend")}
                </Button>
              )}
              {quote.status === "sent" &&
                [...OUTCOMES].reverse().map((outcome) => (
                  <Button
                    key={outcome.action}
                    variant={outcome.variant}
                    disabled={transition.isPending}
                    onClick={() => transition.mutate(outcome)}
                  >
                    {t(`quote.mark.${outcome.action}`)}
                  </Button>
                ))}
              {quote.status === "accepted" && (
                <Button disabled={convert.isPending} onClick={() => convert.mutate()}>
                  {convert.isPending ? t("quote.converting") : t("quote.convert")}
                </Button>
              )}
            </>
            )}
          </>
        }
      />
      <DocumentViewer
        open={sheet === "view"}
        onClose={() => setSheet(null)}
        url={`/quotes/${quote.id}/document`}
        title={`${quote.quote_number} · ${customer?.name ?? ""}`}
      />

      <div className="grid items-start gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          {(quote.title || quote.description) && (
            <section className="card p-5">
              {quote.title && <h2 className="text-base font-semibold text-midnight">{quote.title}</h2>}
              {quote.description && <p className="mt-1 whitespace-pre-line text-sm text-slate-600">{quote.description}</p>}
            </section>
          )}
          <LineItems document={quote} />
          {quote.notes && (
            <section className="card p-5">
              <h2 className="mb-1.5 text-sm font-semibold text-zinc-900">{t("editor.notes")}</h2>
              <p className="whitespace-pre-line text-sm text-zinc-600">{quote.notes}</p>
            </section>
          )}
        </div>
        <aside className="min-w-0">
          <SummaryCard
            rows={[
              [t("invoices.col.customer"), customer?.name ?? "…"],
              [t("invoices.col.issued"), formatDate(quote.issue_date)],
              ...(quote.po_number ? [[t("editor.poNumber"), quote.po_number]] : []),
              ...(quote.reference ? [[t("editor.reference"), quote.reference]] : []),
              [t("quotes.validUntil"), formatDate(quote.expiry_date)],
              [t("document.lineItems"), quote.items.length],
              createdRow(t, quote, team, formatDate),
            ]}
            emphasis={[t("document.totalIncl"), formatMoney(quote.total)]}
          />
        </aside>
      </div>

      <Sheet
        open={sheet === "revise"}
        onClose={close}
        title={t("edit.reviseTitle", { number: quote.quote_number })}
        footer={
          <>
            <Button variant="secondary" onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button disabled={revise.isPending} onClick={() => revise.mutate()}>
              {t("edit.reviseConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">{t("edit.reviseBody")}</p>
      </Sheet>

      <Sheet
        open={sheet === "send"}
        onClose={close}
        title={t("invoice.sendTitle", { number: quote.quote_number })}
        footer={
          <>
            <Button variant="secondary" onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button disabled={send.isPending} onClick={() => send.mutate()}>
              {send.isPending ? t("common.sending") : t("common.send")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-zinc-600">
          {t("quote.sendBody", { total: formatMoney(quote.total) })}
        </p>
        <label className="mt-4 flex items-start gap-3 rounded-lg border border-zinc-200 p-3">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4"
            checked={notify && hasEmail}
            disabled={!hasEmail}
            onChange={(e) => setNotify(e.target.checked)}
          />
          <span className="text-sm">
            <span className="block font-medium text-zinc-900">{t("invoice.emailToCustomer")}</span>
            <span className="text-zinc-500">
              {hasEmail ? recipientEmail : t("invoice.noEmail")}
            </span>
          </span>
        </label>
      </Sheet>
    </div>
  );
}
