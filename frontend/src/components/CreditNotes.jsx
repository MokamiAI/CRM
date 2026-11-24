import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import Sheet from "./Sheet";
import { DocumentViewer } from "./Documents";
import { Button, Field } from "./ui";
import { errorMessage, formatDate, formatMoney } from "../utils/format";

// Sent to the customer: a credit note can reduce it (a draft is edited instead).
export const CREDITABLE = ["sent", "partially_paid", "overdue", "paid"];

export function useCreditNotes(invoiceId) {
  return useQuery({
    queryKey: ["credit-notes", invoiceId],
    queryFn: () => apiClient.get(`/invoices/${invoiceId}/credit-notes`).then((r) => r.data),
    enabled: Boolean(invoiceId),
  });
}

const cents = (n) => Math.round(Number(n) * 100) / 100;

/** Take an amount off an invoice that has gone out, even after a payment.
 *  The invoice keeps its total; the credit note is its own document. */
export function CreditNoteSheet({ open, onClose, invoice, customerEmail, onIssued }) {
  const { t } = useTranslation();
  const creditable = cents(Number(invoice.total) - Number(invoice.amount_credited));
  const paid = Number(invoice.amount_paid);
  const [amount, setAmount] = useState("");
  const [all, setAll] = useState(false);
  const [reason, setReason] = useState("");
  const [notify, setNotify] = useState(true);

  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setAmount("");
      setAll(false);
      setReason("");
    }
  }

  const value = all ? creditable : cents(amount || 0);
  const tooMuch = value > creditable;
  const after = cents(creditable - value - paid); // what's left to pay (negative: a refund)

  const issue = useMutation({
    mutationFn: () =>
      apiClient
        .post(
          `/invoices/${invoice.id}/credit-notes`,
          all ? { kind: "rest", reason } : { kind: "amount", value: value.toFixed(2), reason },
          { params: { notify: notify && Boolean(customerEmail) } }
        )
        .then((r) => r.data),
    onSuccess: (note) => {
      onIssued();
      onClose();
      toast.success(t("credit.issued", { number: note.credit_note_number, amount: formatMoney(note.total) }), {
        description: notify && customerEmail ? t("invoice.emailing", { email: customerEmail }) : undefined,
      });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const valid = value > 0 && !tooMuch && reason.trim().length >= 2;

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t("credit.title", { number: invoice.invoice_number })}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="credit-form" className="btn btn-primary" disabled={!valid || issue.isPending}>
            {issue.isPending ? t("common.saving") : t("credit.issue")}
          </button>
        </>
      }
    >
      <form
        id="credit-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) issue.mutate();
        }}
      >
        <p className="text-sm text-zinc-600">{t("credit.body")}</p>
        <Field
          label={t("credit.amount")}
          error={tooMuch ? t("credit.tooMuch", { amount: formatMoney(creditable) }) : null}
          hint={t("credit.left", { amount: formatMoney(creditable) })}
        >
          <input
            className="input tabular-nums"
            inputMode="decimal"
            placeholder="0.00"
            pattern="\d+(\.\d{1,2})?"
            disabled={all}
            value={all ? creditable.toFixed(2) : amount}
            onChange={(e) => setAmount(e.target.value)}
            data-testid="credit-amount"
          />
        </Field>
        <label className="flex items-center gap-3 text-sm">
          <input type="checkbox" className="h-4 w-4" checked={all} onChange={(e) => setAll(e.target.checked)} />
          <span className="text-zinc-700">{t("credit.all", { amount: formatMoney(creditable) })}</span>
        </label>
        <Field label={t("credit.reason")} hint={t("credit.reasonHint")}>
          <textarea className="input min-h-[76px]" maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="credit-reason" />
        </Field>

        {value > 0 && !tooMuch && (
          <dl className="space-y-1.5 rounded-lg bg-zinc-50 p-3 text-sm ring-1 ring-inset ring-zinc-200">
            <div className="flex justify-between gap-4">
              <dt className="text-zinc-500">{t("document.totalIncl")}</dt>
              <dd className="tabular-nums">{formatMoney(invoice.total)}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-zinc-500">{t("credit.creditNotes")}</dt>
              <dd className="tabular-nums">− {formatMoney(Number(invoice.amount_credited) + value)}</dd>
            </div>
            {paid > 0 && (
              <div className="flex justify-between gap-4">
                <dt className="text-zinc-500">{t("status.paid")}</dt>
                <dd className="tabular-nums">− {formatMoney(paid)}</dd>
              </div>
            )}
            <div className="flex justify-between gap-4 border-t border-zinc-200 pt-1.5 font-semibold text-zinc-900">
              <dt>{after < 0 ? t("credit.refundDue") : t("invoice.balanceDue")}</dt>
              <dd className="tabular-nums">{formatMoney(Math.abs(after))}</dd>
            </div>
            {after < 0 && <p className="pt-1 text-xs text-amber-800">{t("credit.refundHint")}</p>}
          </dl>
        )}

        <label className="flex items-center gap-3 text-sm">
          <input
            type="checkbox"
            className="h-4 w-4"
            checked={notify && Boolean(customerEmail)}
            disabled={!customerEmail}
            onChange={(e) => setNotify(e.target.checked)}
          />
          <span className="text-zinc-700">{customerEmail ? t("credit.email", { email: customerEmail }) : t("invoice.noEmail")}</span>
        </label>
      </form>
    </Sheet>
  );
}

/** The invoice's credit notes: view or print, email again, void a mistake. */
export function CreditNotesCard({ notes, canVoid, canSend, customerName, onChanged }) {
  const { t } = useTranslation();
  const [viewing, setViewing] = useState(null);
  const [voiding, setVoiding] = useState(null);

  const send = useMutation({
    mutationFn: (note) => apiClient.post(`/credit-notes/${note.id}/send`).then((r) => r.data),
    onSuccess: (note) => toast.success(t("credit.sent", { number: note.credit_note_number })),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const voidNote = useMutation({
    mutationFn: (note) => apiClient.post(`/credit-notes/${note.id}/void`).then((r) => r.data),
    onSuccess: (note) => {
      setVoiding(null);
      onChanged();
      toast.success(t("credit.voided", { number: note.credit_note_number }));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (!notes.length) return null;
  return (
    <section className="card overflow-hidden" data-testid="credit-notes">
      <h2 className="border-b border-zinc-100 px-5 py-3.5 text-sm font-semibold text-zinc-900">{t("credit.creditNotes")}</h2>
      <ul className="divide-y divide-zinc-100">
        {notes.map((note) => {
          const isVoid = note.status === "void";
          return (
            <li key={note.id} className="space-y-2 px-5 py-3 text-sm">
              <div className="flex items-baseline justify-between gap-3">
                <p className={`font-medium ${isVoid ? "text-zinc-400 line-through" : "text-zinc-900"}`}>
                  {note.credit_note_number}
                  {isVoid && <span className="ml-2 text-xs font-normal no-underline">{t("status.void")}</span>}
                </p>
                <p className={`shrink-0 font-medium tabular-nums ${isVoid ? "text-zinc-400 line-through" : "text-zinc-900"}`}>− {formatMoney(note.total)}</p>
              </div>
              <p className="break-words text-zinc-500">
                {formatDate(note.issue_date)} · {note.reason}
              </p>
              <div className="flex flex-wrap gap-x-3 gap-y-1">
                <button type="button" className="font-medium text-indigo-600 hover:text-indigo-700" onClick={() => setViewing(note)}>
                  {t("documents.view")}
                </button>
                {!isVoid && canSend && (
                  <button type="button" className="font-medium text-indigo-600 hover:text-indigo-700 disabled:opacity-50" disabled={send.isPending} onClick={() => send.mutate(note)}>
                    {t("credit.emailAgain")}
                  </button>
                )}
                {!isVoid && canVoid && (
                  <button type="button" className="font-medium text-zinc-500 hover:text-red-600" onClick={() => setVoiding(note)}>
                    {t("invoice.void")}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <DocumentViewer
        open={Boolean(viewing)}
        onClose={() => setViewing(null)}
        url={viewing ? `/credit-notes/${viewing.id}/document` : null}
        title={viewing ? `${viewing.credit_note_number} · ${customerName ?? ""}` : ""}
      />

      <Sheet
        open={Boolean(voiding)}
        onClose={() => setVoiding(null)}
        title={t("credit.voidTitle", { number: voiding?.credit_note_number ?? "" })}
        footer={
          <>
            <Button variant="secondary" onClick={() => setVoiding(null)}>
              {t("invoice.keep")}
            </Button>
            <Button variant="danger" disabled={voidNote.isPending} onClick={() => voidNote.mutate(voiding)}>
              {t("credit.voidConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-zinc-600">{t("credit.voidBody", { amount: formatMoney(voiding?.total ?? 0) })}</p>
      </Sheet>
    </section>
  );
}
