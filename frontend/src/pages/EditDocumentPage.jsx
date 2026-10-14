import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useInvoice, usePurchaseOrder, useQuote } from "../hooks/useApi";
import DocumentEditor from "../components/DocumentEditor";
import { BackLink } from "../components/DocumentView";
import { ErrorState, ListSkeleton, PageHeader } from "../components/ui";
import { errorMessage } from "../utils/format";

// What differs between the three documents; the editor is shared.
const KINDS = {
  quote: { path: "quotes", list: "nav.quotes", number: "quote_number", dateField: "expiry_date", dateLabel: "quotes.validUntil", useDoc: useQuote, cacheKey: "quote", lockParty: true },
  invoice: { path: "invoices", list: "nav.invoices", number: "invoice_number", dateField: "due_date", dateLabel: "invoices.dueDate", useDoc: useInvoice, cacheKey: "invoice", lockParty: true },
  purchaseOrder: { path: "purchase-orders", list: "nav.purchaseOrders", number: "po_number", dateField: "delivery_date", dateLabel: "purchases.deliverBy", useDoc: usePurchaseOrder, cacheKey: "purchase-order", lockParty: false },
};

/** Edit a draft quote, invoice or purchase order with the same editor that
 *  made it. Anything past draft says why and links back (sent quotes and
 *  invoices are made editable from their own page first). */
export default function EditDocumentPage({ kind }) {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const k = KINDS[kind];
  const { data: doc, isLoading, isError, refetch } = k.useDoc(id);
  const back = `/${k.path}/${id}`;

  const save = useMutation({
    // Lines, dates, notes and references; the customer stays (lockParty).
    mutationFn: ({ customer_id: _customer, ...payload }) => apiClient.patch(`/${k.path}/${id}`, payload).then((r) => r.data),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: [k.cacheKey, id] });
      queryClient.invalidateQueries({ queryKey: [k.path] });
      toast.success(t("edit.saved", { number: saved[k.number] }));
      navigate(back, { replace: true });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (isLoading) return <ListSkeleton rows={4} />;
  if (isError) return <ErrorState onRetry={refetch} />;

  const header = <PageHeader eyebrow={<BackLink to={back}>{doc[k.number]}</BackLink>} title={t("edit.title", { number: doc[k.number] })} subtitle={t("edit.subtitle")} />;
  if (doc.status !== "draft") {
    return (
      <div className="max-w-3xl">
        {header}
        <div className="card p-5 text-sm text-slate-600">
          <p>{t("edit.notDraft")}</p>
          <Link to={back} className="mt-3 inline-block font-medium text-blue-600 hover:text-blue-800">
            {t("edit.back")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl">
      {header}
      <DocumentEditor
        kind={kind}
        initial={doc}
        lockParty={k.lockParty}
        dateField={k.dateField}
        dateLabel={t(k.dateLabel)}
        submitLabel={t("edit.save")}
        isSubmitting={save.isPending}
        onSubmit={(payload) => save.mutate(payload)}
      />
    </div>
  );
}
