import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import Sheet from "./Sheet";
import { Button, Field, StatusBadge } from "./ui";
import { errorMessage, formatMoney, todayISO } from "../utils/format";

const PRESETS = [25, 30, 50];

/** An accepted quote invoiced in parts: how much is invoiced so far, by
 *  which invoices, and buttons for a deposit or stage and the balance. */
export default function QuoteBilling({ quote, canWrite }) {
  const { t } = useTranslation();
  const [part, setPart] = useState(null); // null | "part" | "balance"
  const { data: billing } = useQuery({
    queryKey: ["quote-billing", quote.id],
    queryFn: () => apiClient.get(`/invoices/from-quote/${quote.id}/billing`).then((r) => r.data),
  });
  if (!billing) return null;

  const total = Number(billing.total);
  const invoiced = Number(billing.invoiced);
  const remaining = Number(billing.remaining);
  const whole = billing.draft_to_replace;
  const pct = total ? Math.min(100, (invoiced / total) * 100) : 0;
  const canPart = canWrite && (remaining > 0 || whole);

  return (
    <section className="card p-5">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-zinc-900">{t("staged.title")}</h2>
        <span className="text-xs font-medium tabular-nums text-zinc-500">{Math.round(pct)}%</span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-zinc-100" aria-hidden="true">
        <div className="h-full rounded-full bg-gradient-to-r from-blue-600 to-violet-500 transition-[width] duration-500 ease-out" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-sm text-zinc-600">
        {t("staged.progress", { invoiced: formatMoney(invoiced), total: formatMoney(total) })}
        {remaining > 0 && <span className="block text-xs text-zinc-500">{t("staged.left", { amount: formatMoney(remaining) })}</span>}
      </p>
      {billing.invoices.length > 0 && (
        <ul className="mt-3 divide-y divide-zinc-100 rounded-lg ring-1 ring-zinc-200">
          {billing.invoices.map((inv) => (
            <li key={inv.id} className="flex items-center gap-2 px-3 py-2 text-sm">
              <Link to={`/invoices/${inv.id}`} className="font-medium text-blue-700 hover:underline">
                {inv.invoice_number}
              </Link>
              <StatusBadge status={inv.status} />
              <span className="ml-auto tabular-nums text-zinc-700">{formatMoney(inv.total)}</span>
            </li>
          ))}
        </ul>
      )}
      {canWrite && billing.draft_edited && (
        <p className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-900 ring-1 ring-inset ring-amber-200">
          {t("staged.draftEdited", { number: billing.draft_edited.invoice_number })}{" "}
          <Link to={`/invoices/${billing.draft_edited.id}`} className="font-semibold underline">
            {t("staged.openDraft")}
          </Link>
        </p>
      )}
      {canPart && (
        <div className="mt-4 flex flex-col gap-2">
          <Button variant="secondary" onClick={() => setPart("part")}>
            {t(billing.invoices.length && !whole ? "staged.addStage" : "staged.addDeposit")}
          </Button>
          {remaining > 0 && billing.invoices.length > 0 && (
            <Button variant="secondary" onClick={() => setPart("balance")}>
              {t("staged.addBalance", { amount: formatMoney(remaining) })}
            </Button>
          )}
          {whole && <p className="text-xs text-zinc-500">{t("staged.splitHint")}</p>}
        </div>
      )}
      <PartSheet open={part !== null} kind={part} onClose={() => setPart(null)} quote={quote} billing={billing} />
    </section>
  );
}

function PartSheet({ open, kind, onClose, quote, billing }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const balance = kind === "balance";
  const first = billing.invoices.length === 0 || Boolean(billing.draft_to_replace);
  const [mode, setMode] = useState("percent");
  const [value, setValue] = useState("50");
  const [label, setLabel] = useState("");
  const [due, setDue] = useState("");

  useEffect(() => {
    if (!open) return;
    setMode("percent");
    setValue(first ? "50" : "");
    setLabel(balance ? t("staged.balanceLabel") : first ? t("staged.depositLabel") : t("staged.stageLabel"));
    setDue("");
  }, [open, balance, first, t]);

  const total = Number(billing.total);
  const left = billing.draft_to_replace ? total : Number(billing.remaining);
  const amount = balance ? left : mode === "percent" ? (total * Number(value || 0)) / 100 : Number(value || 0);
  const tooMuch = amount > left + 0.01;
  const valid = balance || (Number(value) > 0 && !tooMuch && (mode !== "percent" || Number(value) <= 100));

  const create = useMutation({
    mutationFn: () =>
      apiClient
        .post(`/invoices/from-quote/${quote.id}/part`, {
          kind: balance ? "balance" : mode,
          ...(balance ? {} : { value }),
          label: label.trim() || null,
          due_date: due || null,
          replace_draft: Boolean(billing.draft_to_replace),
        })
        .then((r) => r.data),
    onSuccess: (invoice) => {
      queryClient.invalidateQueries({ queryKey: ["quote-billing", quote.id] });
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      queryClient.invalidateQueries({ queryKey: ["quote", quote.id] });
      toast.success(t("staged.created", { number: invoice.invoice_number }));
      onClose();
      navigate(`/invoices/${invoice.id}`);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t(balance ? "staged.balanceTitle" : first ? "staged.depositTitle" : "staged.stageTitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!valid || create.isPending} onClick={() => create.mutate()}>
            {t("staged.create", { amount: formatMoney(Math.max(0, Math.min(amount, left))) })}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <p className="text-sm text-zinc-600">{t("staged.intro", { number: quote.quote_number, total: formatMoney(total) })}</p>
        {!balance && (
          <>
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label={t("staged.how")}>
              {["percent", "amount"].map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={mode === m}
                  onClick={() => {
                    setMode(m);
                    setValue("");
                  }}
                  className={`pressable rounded-lg px-3 py-2 text-sm font-semibold ring-1 ring-inset ${mode === m ? "bg-blue-600 text-white ring-blue-600" : "bg-white text-zinc-700 ring-zinc-200 hover:bg-zinc-50"}`}
                >
                  {t(`staged.mode.${m}`)}
                </button>
              ))}
            </div>
            <Field label={t(mode === "percent" ? "staged.percentLabel" : "staged.amountLabel")} error={tooMuch ? t("staged.tooMuch", { amount: formatMoney(left) }) : undefined}>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  className="input !w-40"
                  type="number"
                  inputMode="decimal"
                  min="0"
                  max={mode === "percent" ? 100 : undefined}
                  step={mode === "percent" ? 1 : 0.01}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  autoFocus
                />
                {mode === "percent" &&
                  PRESETS.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setValue(String(p))}
                      className={`rounded-full px-3 py-1 text-sm font-medium ring-1 ring-inset ${Number(value) === p ? "bg-blue-50 text-blue-700 ring-blue-200" : "text-zinc-600 ring-zinc-200 hover:bg-zinc-50"}`}
                    >
                      {p}%
                    </button>
                  ))}
              </div>
            </Field>
          </>
        )}
        <Field label={t("staged.labelField")} hint={t("staged.labelHint")}>
          <input className="input" maxLength={60} value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
        <Field label={t("staged.due")} hint={t("staged.dueHint")}>
          <input className="input !w-48" type="date" min={todayISO()} value={due} onChange={(e) => setDue(e.target.value)} />
        </Field>
        <div className="rounded-xl bg-zinc-50 p-4 ring-1 ring-inset ring-zinc-200">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{t("staged.thisInvoice")}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-zinc-900">{formatMoney(Math.max(0, Math.min(amount, left)))}</p>
          <p className="mt-1 text-xs text-zinc-500">{t("staged.vatNote")}</p>
        </div>
        {billing.draft_to_replace && (
          <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-inset ring-amber-200">
            {t("staged.replaces", { number: billing.draft_to_replace.invoice_number })}
          </p>
        )}
      </div>
    </Sheet>
  );
}
