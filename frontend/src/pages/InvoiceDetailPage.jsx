import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import apiClient from "../services/apiClient";
import { useCustomerMap, useInvoice, usePayments, useReminders, useTeamMap } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import Sheet from "../components/Sheet";
import { DocumentViewer } from "../components/Documents";
import { BackLink, LineItems, SummaryCard, createdRow } from "../components/DocumentView";
import { Button, ButtonLink, ErrorState, Field, ListSkeleton, PageHeader, StatusBadge } from "../components/ui";
import { errorMessage, formatDate, formatMoney, todayISO } from "../utils/format";

const PAYMENT_METHODS = ["eft", "bank_transfer", "card", "cash", "other"];

const PAYABLE = ["sent", "partially_paid", "overdue"];

// "schedule:-3" / "schedule:7" / "manual:<timestamp>" (reminder_service.py)
function describeReminder(reminderType) {
  const [kind, value] = reminderType.split(/:(.*)/);
  if (kind === "manual") return i18n.t("timeline.reminderManual");
  const days = Number(value);
  if (days === 0) return i18n.t("invoice.reminderOnDue");
  return i18n.t(days < 0 ? "invoice.reminderBefore" : "invoice.reminderAfter", { count: Math.abs(days) });
}
const VOIDABLE = ["draft", "sent", "overdue"];
// Already emailed: can be emailed again ("please resend").
const RESENDABLE = ["sent", "partially_paid", "overdue", "paid"];

export default function InvoiceDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const canVoid = ["admin", "manager"].includes(user?.role);
  const isAdmin = user?.role === "admin";

  const { data: invoice, isLoading, isError, refetch } = useInvoice(id);
  const { data: payments = [] } = usePayments(id);
  const { data: reminders = [] } = useReminders(id);
  const customer = useCustomerMap().get(invoice?.customer_id);
  const team = useTeamMap();

  const [sheet, setSheet] = useState(null); // "send" | "pay" | "void" | "delete" | "correct" | null
  // A row's pencil on a sent invoice arrives as ?edit=1: ask once.
  const [searchParams, setSearchParams] = useSearchParams();
  if (invoice && searchParams.get("edit") && !sheet) {
    setSearchParams({}, { replace: true });
    if (canVoid && ["sent", "overdue"].includes(invoice.status) && Number(invoice.amount_paid) === 0) setSheet("correct");
  }
  const close = () => setSheet(null);

  const queryClient = useQueryClient();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["invoice", id] });
    queryClient.invalidateQueries({ queryKey: ["payments", id] });
    queryClient.invalidateQueries({ queryKey: ["reminders", id] });
    queryClient.invalidateQueries({ queryKey: ["invoices"] });
  };
  const onError = (error) => toast.error(errorMessage(error));

  const [notify, setNotify] = useState(true);
  const send = useMutation({
    mutationFn: () => apiClient.post(`/invoices/${id}/send`, null, { params: { notify } }),
    onSuccess: () => {
      refresh();
      close();
      toast.success(t("invoice.sent"), {
        description: notify && customer?.email ? t("invoice.emailing", { email: customer.email }) : t("invoice.sentNoEmail"),
      });
    },
    onError,
  });

  const remind = useMutation({
    mutationFn: () => apiClient.post(`/invoices/${id}/remind`),
    onSuccess: () => {
      refresh();
      close();
      toast.success(t("invoice.reminderSent"), { description: customer?.email });
    },
    onError,
  });

  const resend = useMutation({
    mutationFn: () => apiClient.post(`/invoices/${id}/resend`),
    onSuccess: () => toast.success(t("invoice.resent"), { description: customer?.email }),
    onError,
  });

  const voidInvoice = useMutation({
    mutationFn: () => apiClient.post(`/invoices/${id}/void`),
    onSuccess: () => {
      refresh();
      close();
      toast.success(t("invoice.voided"));
    },
    onError,
  });

  // Edit on a sent, unpaid invoice: void it and open a draft copy to fix.
  const correct = useMutation({
    mutationFn: () => apiClient.post(`/invoices/${id}/correct`).then((r) => r.data),
    onSuccess: (copy) => {
      refresh();
      close();
      toast.success(t("edit.corrected", { old: invoice.invoice_number, number: copy.invoice_number }));
      navigate(`/invoices/${copy.id}/edit`);
    },
    onError,
  });

  const remove = useMutation({
    mutationFn: () => apiClient.delete(`/invoices/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      toast.success(t("invoice.draftDeleted"));
      navigate("/invoices", { replace: true });
    },
    onError,
  });

  const deletePayment = useMutation({
    mutationFn: (paymentId) => apiClient.delete(`/payments/${paymentId}`),
    onSuccess: () => {
      refresh();
      toast.success(t("invoice.paymentRemoved"));
    },
    onError,
  });

  if (isLoading) return <ListSkeleton rows={4} />;
  if (isError) return <ErrorState onRetry={refetch} />;

  const balance = Number(invoice.total) - Number(invoice.amount_paid);
  const hasEmail = Boolean(customer?.email);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={<BackLink to="/invoices">{t("nav.invoices")}</BackLink>}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {invoice.invoice_number} <StatusBadge status={invoice.status} />
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
              {invoice.status === "draft" && (
                <>
                  <Button variant="danger" onClick={() => setSheet("delete")}>
                    {t("invoice.deleteDraft")}
                  </Button>
                  <ButtonLink variant="secondary" to={`/invoices/${id}/edit`}>
                    {t("common.edit")}
                  </ButtonLink>
                </>
              )}
              {canVoid && ["sent", "overdue"].includes(invoice.status) && Number(invoice.amount_paid) === 0 && (
                <Button variant="secondary" onClick={() => setSheet("correct")}>
                  {t("common.edit")}
                </Button>
              )}
              {canVoid && VOIDABLE.includes(invoice.status) && (
                <Button variant="secondary" onClick={() => setSheet("void")}>
                  {t("invoice.void")}
                </Button>
              )}
              {RESENDABLE.includes(invoice.status) && hasEmail && (
                <Button variant="secondary" disabled={resend.isPending} onClick={() => resend.mutate()}>
                  {resend.isPending ? t("common.sending") : t("invoice.resend")}
                </Button>
              )}
              {PAYABLE.includes(invoice.status) && hasEmail && (
                <Button variant="secondary" onClick={() => setSheet("remind")}>
                  {t("invoice.sendReminder")}
                </Button>
              )}
              {PAYABLE.includes(invoice.status) && <Button onClick={() => setSheet("pay")}>{t("invoice.recordPayment")}</Button>}
              {invoice.status === "draft" && <Button onClick={() => setSheet("send")}>{t("invoice.send")}</Button>}
            </>
            )}
          </>
        }
      />

      <DocumentViewer
        open={sheet === "view"}
        onClose={() => setSheet(null)}
        url={`/invoices/${invoice.id}/document`}
        title={`${invoice.invoice_number} · ${customer?.name ?? ""}`}
      />

      <div className="grid items-start gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <LineItems document={invoice} />
          {invoice.notes && (
            <section className="card p-5">
              <h2 className="mb-1.5 text-sm font-semibold text-zinc-900">{t("editor.notes")}</h2>
              <p className="whitespace-pre-line text-sm text-zinc-600">{invoice.notes}</p>
            </section>
          )}
        </div>

        <aside className="min-w-0 space-y-6">
          <SummaryCard
            rows={[
              [t("invoices.col.customer"), customer?.name ?? "…"],
              [t("invoices.col.issued"), formatDate(invoice.issue_date)],
              ...(invoice.po_number ? [[t("editor.poNumber"), invoice.po_number]] : []),
              ...(invoice.reference ? [[t("editor.reference"), invoice.reference]] : []),
              [t("invoices.col.due"), formatDate(invoice.due_date)],
              [t("document.totalIncl"), formatMoney(invoice.total)],
              [t("status.paid"), formatMoney(invoice.amount_paid)],
              createdRow(t, invoice, team, formatDate),
            ]}
            emphasis={[t("invoice.balanceDue"), formatMoney(balance)]}
          />

          {payments.length > 0 && (
        <section className="card overflow-hidden">
          <h2 className="border-b border-zinc-100 px-5 py-3.5 text-sm font-semibold text-zinc-900">{t("invoice.payments")}</h2>
          <ul className="divide-y divide-zinc-100">
            {payments.map((payment) => (
              <li key={payment.id} className="flex items-center justify-between gap-4 px-5 py-3 text-sm">
                <div className="min-w-0">
                  <p className="font-medium tabular-nums text-zinc-900">{formatMoney(payment.amount)}</p>
                  <p className="truncate text-zinc-500">
                    {formatDate(payment.paid_at)} · {t(`paymentMethod.${payment.method}`)}
                    {payment.reference && ` · ${payment.reference}`}
                  </p>
                </div>
                {isAdmin && invoice.status !== "void" && (
                  <button
                    type="button"
                    disabled={deletePayment.isPending}
                    onClick={() => deletePayment.mutate(payment.id)}
                    className="pressable shrink-0 rounded-md px-2 py-1 text-zinc-400 hover:bg-zinc-100 hover:text-red-600"
                  >
                    {t("editor.remove")}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
          )}

          {reminders.length > 0 && (
        <section className="card overflow-hidden">
          <h2 className="border-b border-zinc-100 px-5 py-3.5 text-sm font-semibold text-zinc-900">{t("invoice.remindersSent")}</h2>
          <ul className="divide-y divide-zinc-100">
            {reminders.map((reminder) => (
              <li key={reminder.id} className="flex items-center justify-between gap-4 px-5 py-3 text-sm">
                <span className="text-zinc-700">{describeReminder(reminder.reminder_type)}</span>
                <span className="shrink-0 text-zinc-500">{formatDate(reminder.sent_at)}</span>
              </li>
            ))}
          </ul>
        </section>
          )}
        </aside>
      </div>

      <Sheet
        open={sheet === "remind"}
        onClose={close}
        title={t("invoice.remindTitle")}
        footer={
          <>
            <Button variant="secondary" onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button disabled={remind.isPending} onClick={() => remind.mutate()}>
              {remind.isPending ? t("common.sending") : t("invoice.sendReminder")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-zinc-600">
          {t("invoice.remindBody", { email: customer?.email, amount: formatMoney(balance), number: invoice.invoice_number })}
        </p>
      </Sheet>

      <Sheet
        open={sheet === "send"}
        onClose={close}
        title={t("invoice.sendTitle", { number: invoice.invoice_number })}
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
          {t("invoice.sendBody", { total: formatMoney(invoice.total), date: formatDate(invoice.due_date) })}
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

      <RecordPaymentSheet
        open={sheet === "pay"}
        onClose={close}
        invoice={invoice}
        balance={balance}
        customerEmail={customer?.email}
        onRecorded={refresh}
      />

      <Sheet
        open={sheet === "correct"}
        onClose={close}
        title={t("edit.correctTitle", { number: invoice.invoice_number })}
        footer={
          <>
            <Button variant="secondary" onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button disabled={correct.isPending} onClick={() => correct.mutate()}>
              {t("edit.correctConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">{t("edit.correctBody", { number: invoice.invoice_number })}</p>
      </Sheet>

      <Sheet
        open={sheet === "void"}
        onClose={close}
        title={t("invoice.voidTitle", { number: invoice.invoice_number })}
        footer={
          <>
            <Button variant="secondary" onClick={close}>
              {t("invoice.keep")}
            </Button>
            <Button variant="danger" disabled={voidInvoice.isPending} onClick={() => voidInvoice.mutate()}>
              {t("invoice.voidInvoice")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-zinc-600">
          {t("invoice.voidBody")}
        </p>
      </Sheet>

      <Sheet
        open={sheet === "delete"}
        onClose={close}
        title={t("invoice.deleteTitle")}
        footer={
          <>
            <Button variant="secondary" onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
              {t("common.delete")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-zinc-600">
          {t("invoice.deleteBody", { number: invoice.invoice_number })}
        </p>
      </Sheet>
    </div>
  );
}

function RecordPaymentSheet({ open, onClose, invoice, balance, customerEmail, onRecorded }) {
  const { t } = useTranslation();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("eft");
  const [reference, setReference] = useState("");
  const [paidOn, setPaidOn] = useState(todayISO());
  const [notify, setNotify] = useState(true);

  // Reset to the outstanding balance each time the sheet opens: most
  // payments settle the invoice in full.
  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setAmount(balance.toFixed(2));
      setReference("");
      setPaidOn(todayISO());
    }
  }

  const record = useMutation({
    mutationFn: () =>
      apiClient.post(
        `/invoices/${invoice.id}/payments`,
        {
          amount,
          method,
          reference: reference || null,
          // Midday local time: a date-only payment shouldn't slip to the
          // previous day when stored as UTC.
          paid_at: new Date(`${paidOn}T12:00:00`).toISOString(),
        },
        { params: { notify: notify && Boolean(customerEmail) } }
      ),
    onSuccess: () => {
      onRecorded();
      onClose();
      toast.success(t("invoice.paymentRecorded", { amount: formatMoney(amount) }), {
        description: Number(amount) >= balance ? t("invoice.paidInFull") : undefined,
      });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  function handleSubmit(event) {
    event.preventDefault();
    record.mutate();
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t("invoice.recordPayment")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="payment-form" className="btn btn-primary" disabled={record.isPending}>
            {record.isPending ? t("common.saving") : t("invoice.recordPayment")}
          </button>
        </>
      }
    >
      <form id="payment-form" onSubmit={handleSubmit} className="space-y-4">
        <Field label={t("invoices.col.amount")} hint={t("invoice.outstanding", { amount: formatMoney(balance) })}>
          <input
            className="input tabular-nums"
            inputMode="decimal"
            required
            pattern="\d+(\.\d{1,2})?"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label={t("invoice.method")}>
            <select className="input" value={method} onChange={(e) => setMethod(e.target.value)}>
              {PAYMENT_METHODS.map((value) => (
                <option key={value} value={value}>
                  {t(`paymentMethod.${value}`)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("invoice.date")}>
            <input className="input" type="date" required value={paidOn} max={todayISO()} onChange={(e) => setPaidOn(e.target.value)} />
          </Field>
        </div>
        <Field label={t("invoice.reference")}>
          <input className="input" value={reference} onChange={(e) => setReference(e.target.value)} />
        </Field>
        <label className="flex items-center gap-3 text-sm">
          <input
            type="checkbox"
            className="h-4 w-4"
            checked={notify && Boolean(customerEmail)}
            disabled={!customerEmail}
            onChange={(e) => setNotify(e.target.checked)}
          />
          <span className="text-zinc-700">
            {customerEmail ? t("invoice.emailReceipt", { email: customerEmail }) : t("invoice.noReceipt")}
          </span>
        </label>
      </form>
    </Sheet>
  );
}
