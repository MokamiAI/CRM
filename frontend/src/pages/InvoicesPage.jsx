import { KpiCard, StatStrip } from "../components/dashboard";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useCustomerMap, useInvoices, useReportSummary } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import DocumentEditor from "../components/DocumentEditor";
import { BackLink } from "../components/DocumentView";
import InvoiceList from "../components/InvoiceList";
import { ClientFilter } from "../components/Documents";
import {
  ButtonLink,
  EmptyState,
  ErrorState,
  FilterChips,
  ListSkeleton,
  PageHeader,
  PlusIcon,
} from "../components/ui";
import { errorMessage, formatMoneyWhole } from "../utils/format";
import ImportExportButtons from "../components/ImportExport";

const STATUS_FILTERS = [
  { value: "", key: "common.all" },
  { value: "draft", key: "status.draft" },
  { value: "sent", key: "status.sent" },
  { value: "partially_paid", key: "status.partially_paid" },
  { value: "overdue", key: "status.overdue" },
  { value: "paid", key: "status.paid" },
  { value: "void", key: "status.void" },
];

export function InvoicesPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [status, setStatus] = useState("");
  const [params, setParams] = useSearchParams();
  const client = params.get("client") ?? "";
  const setClient = (id) => setParams(id ? { client: id } : {}, { replace: true });
  const { data, isLoading, isError, refetch } = useInvoices({ ...(status ? { status } : {}), ...(client ? { customer_id: client } : {}) });
  const customers = useCustomerMap();
  const { data: summary } = useReportSummary();
  const { data: drafts = [] } = useInvoices({ status: "draft" });

  return (
    <>
      <PageHeader
        title={t("nav.invoices")}
        subtitle={data ? t(status ? "invoices.count" : "invoices.countTotal", { count: data.length }) : undefined}
        actions={
          <>
            <ImportExportButtons entity="invoices" />
            <ButtonLink variant="secondary" to="/invoices/aging">
              {t("aging.link")}
            </ButtonLink>
            <ButtonLink variant="secondary" to="/invoices/recurring">
              {t("recurring.link")}
            </ButtonLink>
            {user?.role !== "viewer" && (
              <ButtonLink to="/invoices/new">
                <PlusIcon className="h-4 w-4" /> {t("dashboard.newInvoice")}
              </ButtonLink>
            )}
          </>
        }
      />
      {summary && (
        <StatStrip>
          <KpiCard compact to="/invoices/aging" icon="invoice" tone="amber" label={t("dashboard.kpi.outstanding")} value={formatMoneyWhole(summary.outstanding)} detail={t("dashboard.acrossInvoices", { count: summary.open_invoice_count })} />
          <KpiCard compact icon="invoice" tone="rose" label={t("status.overdue")} value={formatMoneyWhole(summary.overdue)} detail={t("lists.chase")} />
          <KpiCard compact icon="cash" tone="emerald" label={t("dashboard.kpi.collected")} value={formatMoneyWhole(summary.collected_by_month.at(-1).total)} detail={t("dashboard.kpi.thisMonth")} />
          <KpiCard compact icon="invoice" tone="blue" label={t("lists.drafts")} value={drafts.length} detail={t("lists.notSent", { count: drafts.length })} />
        </StatStrip>
      )}
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
          title={t(status || client ? "invoices.noneWithStatus" : "invoices.none")}
          description={status ? undefined : t("invoices.noneHint")}
        />
      ) : (
        <InvoiceList invoices={data} customers={customers} />
      )}
    </>
  );
}

export function NewInvoicePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const create = useMutation({
    mutationFn: (payload) => apiClient.post("/invoices", payload).then((res) => res.data),
    onSuccess: (invoice) => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      toast.success(t("invoices.draftCreated", { number: invoice.invoice_number }));
      navigate(`/invoices/${invoice.id}`, { replace: true });
    },
    onError: (error) => toast.error(errorMessage(error, t("invoices.createFailed"))),
  });

  return (
    <div className="max-w-3xl">
      <PageHeader eyebrow={<BackLink to="/invoices">{t("nav.invoices")}</BackLink>} title={t("dashboard.newInvoice")} subtitle={t("invoices.draftNote")} />
      <DocumentEditor
        dateField="due_date"
        dateLabel={t("invoices.dueDate")}
        dateHint={t("invoices.dueDateHint")}
        submitLabel={t("invoices.saveDraft")}
        isSubmitting={create.isPending}
        initialCustomerId={searchParams.get("customer") ?? undefined}
        onSubmit={(payload) => create.mutate(payload)}
      />
    </div>
  );
}
