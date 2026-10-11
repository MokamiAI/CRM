import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import apiClient from "../services/apiClient";
import { useCustomerMap, useQuote, useQuotes } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import DocumentEditor from "../components/DocumentEditor";
import { BackLink, LineItems, SummaryCard } from "../components/DocumentView";
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
import { errorMessage, formatDate, formatMoney, formatShortDate } from "../utils/format";

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

  return (
    <>
      <PageHeader
        title={t("nav.quotes")}
        subtitle={data ? t(status ? "quotes.count" : "quotes.countTotal", { count: data.length }) : undefined}
        actions={
          user?.role !== "viewer" && (
            <ButtonLink to="/quotes/new">
              <PlusIcon className="h-4 w-4" /> {t("quotes.new")}
            </ButtonLink>
          )
        }
      />
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

function QuoteList({ quotes, customers }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
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
                  <span className="truncate text-zinc-700">{nameOf(quote)}</span>
                </div>
              </td>
              <td className="whitespace-nowrap text-zinc-500">{formatShortDate(quote.issue_date)}</td>
              <td className="whitespace-nowrap text-zinc-500">{quote.expiry_date ? formatShortDate(quote.expiry_date) : "—"}</td>
              <td>
                <StatusBadge status={quote.status} />
              </td>
              <td className="whitespace-nowrap text-right font-medium tabular-nums text-zinc-900">{formatMoney(quote.total)}</td>
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
      toast.success(t("invoices.draftCreated", { number: quote.quote_number }));
      navigate(`/quotes/${quote.id}`, { replace: true });
    },
    onError: (error) => toast.error(errorMessage(error, t("quotes.createFailed"))),
  });

  return (
    <div className="max-w-3xl">
      <PageHeader eyebrow={<BackLink to="/quotes">{t("nav.quotes")}</BackLink>} title={t("quotes.new")} subtitle={t("invoices.draftNote")} />
      <DocumentEditor
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
  const [sheet, setSheet] = useState(null);
  const [notify, setNotify] = useState(true);
  const close = () => setSheet(null);

  const queryClient = useQueryClient();
  const refresh = () => {
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
        description: notify && customer?.email ? t("invoice.emailing", { email: customer.email }) : t("invoice.sentNoEmail"),
      });
    },
    onError,
  });

  const transition = useMutation({
    mutationFn: (outcome) => apiClient.post(`/quotes/${id}/${outcome.action}`).then(() => outcome),
    onSuccess: (outcome) => {
      refresh();
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

  const hasEmail = Boolean(customer?.email);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={<BackLink to="/quotes">{t("nav.quotes")}</BackLink>}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {quote.quote_number} <StatusBadge status={quote.status} />
          </span>
        }
        subtitle={customer?.name}
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
                  <Button onClick={() => setSheet("send")}>{t("quote.send")}</Button>
                </>
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
              [t("quotes.validUntil"), formatDate(quote.expiry_date)],
              [t("document.lineItems"), quote.items.length],
            ]}
            emphasis={[t("document.total"), formatMoney(quote.total)]}
          />
        </aside>
      </div>

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
              {hasEmail ? customer.email : t("invoice.noEmail")}
            </span>
          </span>
        </label>
      </Sheet>
    </div>
  );
}
