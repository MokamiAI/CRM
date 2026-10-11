import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useCustomers, useProducts } from "../hooks/useApi";
import { Button, Field } from "./ui";
import { formatMoney, todayISO } from "../utils/format";

// Mirrors backend/app/services/pricing.py: tax per line, each step rounded
// half-up to the cent, in integer cents to dodge float drift. A preview
// only; the server computes the stored totals.
function toCents(value) {
  return Math.round((Number(value) + Number.EPSILON) * 100);
}

export function computeTotals(items) {
  let subtotal = 0;
  let tax = 0;
  for (const item of items) {
    const qty = Number(item.quantity) || 0;
    const lineCents = toCents(qty * (Number(item.unit_price) || 0));
    subtotal += lineCents;
    tax += Math.round((lineCents * (Number(item.tax_rate) || 0)) / 100);
  }
  return { subtotal: subtotal / 100, tax: tax / 100, total: (subtotal + tax) / 100 };
}

let nextKey = 1;
const blankItem = () => ({
  key: nextKey++,
  product_id: null,
  description: "",
  quantity: "1",
  unit_price: "",
  tax_rate: "15",
});

/**
 * Shared create form for invoices and quotes: customer, dates, line items
 * with product pick-to-fill, and a live total.
 * `dateField` is "due_date" (invoice, optional: defaults from payment
 * terms) or "expiry_date" (quote).
 */
export default function DocumentEditor({ dateField, dateLabel, dateHint, submitLabel, isSubmitting, onSubmit, initialCustomerId }) {
  const { t } = useTranslation();
  const { data: customers = [] } = useCustomers({ is_active: true });
  const { data: products = [] } = useProducts({ is_active: true });

  const [customerId, setCustomerId] = useState(initialCustomerId ?? "");
  const [issueDate, setIssueDate] = useState(todayISO());
  const [secondDate, setSecondDate] = useState("");
  const [notes, setNotes] = useState("");
  const [poNumber, setPoNumber] = useState("");
  const [items, setItems] = useState(() => [blankItem()]);

  const totals = computeTotals(items);

  function updateItem(key, patch) {
    setItems((prev) => prev.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  }

  function pickProduct(key, productId) {
    const product = products.find((p) => p.id === productId);
    updateItem(
      key,
      product
        ? {
            product_id: product.id,
            description: product.name,
            unit_price: String(Number(product.unit_price)),
            tax_rate: String(Number(product.tax_rate)),
          }
        : { product_id: null }
    );
  }

  function handleSubmit(event) {
    event.preventDefault();
    onSubmit({
      customer_id: customerId,
      issue_date: issueDate,
      ...(secondDate && { [dateField]: secondDate }),
      notes: notes || null,
      po_number: poNumber.trim() || null,
      items: items.map(({ product_id, description, quantity, unit_price, tax_rate }) => ({
        product_id,
        description,
        quantity,
        unit_price: unit_price || "0",
        tax_rate: tax_rate || "0",
      })),
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5 pb-24 md:pb-0">
      <section className="card space-y-4 p-4 sm:p-5">
        <Field label={t("editor.customer")}>
          <select className="input" required value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
            <option value="" disabled>
              {t("dealForm.chooseCustomer")}
            </option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label={t("editor.issueDate")}>
            <input className="input" type="date" required value={issueDate} onChange={(e) => setIssueDate(e.target.value)} />
          </Field>
          <Field label={dateLabel} hint={dateHint}>
            <input
              className="input"
              type="date"
              min={issueDate}
              value={secondDate}
              onChange={(e) => setSecondDate(e.target.value)}
            />
          </Field>
        </div>
      </section>

      <section className="card p-4 sm:p-5">
        <h2 className="mb-4 text-sm font-semibold text-zinc-900">{t("document.lineItems")}</h2>
        <ol className="space-y-4">
          {items.map((item, index) => (
            <li key={item.key} className="rounded-lg border border-zinc-200/80 bg-zinc-50/50 p-3 sm:p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-400">{t("editor.item", { n: index + 1 })}</span>
                {items.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setItems((prev) => prev.filter((i) => i.key !== item.key))}
                    className="pressable rounded-md px-2 py-1 text-sm text-zinc-500 hover:bg-zinc-100 hover:text-red-600"
                  >
                    {t("editor.remove")}
                  </button>
                )}
              </div>
              <div className="space-y-3">
                <select
                  className="input"
                  aria-label={t("editor.product")}
                  value={item.product_id ?? ""}
                  onChange={(e) => pickProduct(item.key, e.target.value)}
                >
                  <option value="">{t("editor.customItem")}</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} · {formatMoney(p.unit_price)}
                    </option>
                  ))}
                </select>
                <input
                  className="input"
                  aria-label={t("editor.description")}
                  placeholder={t("editor.description")}
                  required
                  value={item.description}
                  onChange={(e) => updateItem(item.key, { description: e.target.value })}
                />
                <div className="grid grid-cols-3 gap-2">
                  <Field label={t("editor.qty")}>
                    <input
                      className="input tabular-nums"
                      inputMode="decimal"
                      required
                      pattern="\d+(\.\d{1,2})?"
                      value={item.quantity}
                      onChange={(e) => updateItem(item.key, { quantity: e.target.value })}
                    />
                  </Field>
                  <Field label={t("editor.unitPrice")}>
                    <input
                      className="input tabular-nums"
                      inputMode="decimal"
                      required
                      pattern="\d+(\.\d{1,2})?"
                      value={item.unit_price}
                      onChange={(e) => updateItem(item.key, { unit_price: e.target.value })}
                    />
                  </Field>
                  <Field label={t("editor.taxPercent")}>
                    <input
                      className="input tabular-nums"
                      inputMode="decimal"
                      pattern="\d+(\.\d{1,2})?"
                      value={item.tax_rate}
                      onChange={(e) => updateItem(item.key, { tax_rate: e.target.value })}
                    />
                  </Field>
                </div>
              </div>
            </li>
          ))}
        </ol>
        <Button variant="secondary" className="mt-4 w-full" onClick={() => setItems((prev) => [...prev, blankItem()])}>
          {t("editor.addLine")}
        </Button>
      </section>

      <section className="card p-4 sm:p-5">
        <Field label={t("editor.poNumber")} hint={t("editor.poNumberHint")} className="mb-4">
          <input className="input" maxLength={60} value={poNumber} onChange={(e) => setPoNumber(e.target.value)} placeholder="PO-1234" />
        </Field>
        <Field label={t("editor.notes")} hint={t("editor.notesHint")}>
          <textarea className="input" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
        <p className="mt-3 text-xs text-zinc-500">
          {t("editor.bankingHint")}{" "}
          <Link to="/settings?tab=documents" className="font-medium text-indigo-600 hover:text-indigo-700">
            {t("editor.bankingLink")}
          </Link>
        </p>
      </section>

      {/* Totals + submit: pinned above the tab bar on phones so the total is
          always in view while editing items; inline on larger screens. */}
      <div className="fixed inset-x-0 bottom-[var(--tabbar-height)] z-10 border-t border-zinc-200/80 bg-white/90 px-4 py-3 backdrop-blur-md md:static md:rounded-xl md:border md:bg-white md:px-5 md:py-4 md:shadow-card md:backdrop-blur-none">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4">
          <div className="text-sm">
            <p className="text-xs text-zinc-500">
              {t("document.subtotal")} {formatMoney(totals.subtotal)} · {t("document.tax")} {formatMoney(totals.tax)}
            </p>
            <p className="text-xl font-semibold tracking-tight text-zinc-900">{formatMoney(totals.total)}</p>
          </div>
          <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
            {isSubmitting ? t("common.saving") : submitLabel}
          </button>
        </div>
      </div>
    </form>
  );
}
