import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useCompany, useCustomers, usePipelineAccounts, useLineTemplates, useProducts, useSuppliers } from "../hooks/useApi";
import { Button, Field } from "./ui";
import PartyCombobox from "./PartyCombobox";
import CustomerFormSheet from "./CustomerFormSheet";
import SupplierSheet from "./SupplierSheet";
import { errorMessage, formatMoney, todayISO } from "../utils/format";

// Mirrors backend/app/services/pricing.py: tax per line, each step rounded
// half-up to the cent, in integer cents to dodge float drift. A preview
// only; the server computes the stored totals.
function toCents(value) {
  return Math.round((Number(value) + Number.EPSILON) * 100);
}

function lineCents(item) {
  return toCents((Number(item.quantity) || 0) * (Number(item.unit_price) || 0));
}

export function computeTotals(items) {
  let subtotal = 0;
  let tax = 0;
  for (const item of items) {
    const cents = lineCents(item);
    subtotal += cents;
    tax += Math.round((cents * (Number(item.tax_rate) || 0)) / 100);
  }
  return { subtotal: subtotal / 100, tax: tax / 100, total: (subtotal + tax) / 100 };
}

let nextKey = 1;
// New lines start at 15% VAT, or 0% on sales documents of a company not
// registered for VAT (see DocumentEditor's `vatRate`).
let defaultVat = "15";
const blankItem = () => ({ key: nextKey++, product_id: null, description: "", quantity: "1", unit_price: "", tax_rate: defaultVat });
const isBlank = (item) => !item.description.trim() && !item.unit_price;

/** True on screens wide enough for the line-items table. */
function useWide() {
  const query = "(min-width: 768px)";
  const [wide, setWide] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setWide(list.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, []);
  return wide;
}

const NUMBER = { inputMode: "decimal", pattern: "\\d+(\\.\\d{1,2})?" };

/**
 * Shared create form for quotes, invoices and purchase orders: who it's for
 * (a customer, or a supplier for a purchase order), dates, references, line
 * items as a table (cards on phones) with product suggestions and saved
 * sets, and a live total.
 */
// `children` adds fields to the first card (e.g. a recurring schedule's);
// `issueLabel` renames the issue date; without `dateField` the second date is left out.
/** `initial`: a saved quote, invoice, purchase order or schedule to edit
 *  (its party, dates, notes, reference and lines). `lockParty`: the customer
 *  can't change on an existing document. */
export default function DocumentEditor({ kind = "invoice", dateField, dateLabel, dateHint, issueLabel, submitLabel, isSubmitting, onSubmit, initialCustomerId, initial, lockParty = false, children }) {
  const { t } = useTranslation();
  const purchase = kind === "purchaseOrder";
  const { data: company } = useCompany();
  const notVatRegistered = !purchase && company && !company.vat_registered;
  defaultVat = notVatRegistered ? "0" : "15";
  const { data: customers = [] } = useCustomers({ is_active: true });
  const { data: suppliers = [] } = useSuppliers();
  const { data: pipelineAccounts = [] } = usePipelineAccounts({ enabled: kind === "quote" });
  const parties = purchase ? suppliers : kind === "quote" ? pipelineAccounts : customers;
  const { data: products = [] } = useProducts({ is_active: true });
  const wide = useWide();

  // The customer (or supplier): chosen from the list, or a new name typed
  // in, which is added when the document is saved.
  const [party, setParty] = useState({ id: initial?.[purchase ? "supplier_id" : "customer_id"] ?? initialCustomerId ?? null, name: "" });
  const [addingParty, setAddingParty] = useState(false);
  // New line items (typed, not picked) are kept as products for next time.
  const [rememberItems, setRememberItems] = useState(true);
  const queryClient = useQueryClient();
  // A new name chosen from the list: its form opens now, with that name.
  const [newParty, setNewParty] = useState(null);
  const partyAdded = (saved) => {
    setParty({ id: saved.id, name: saved.name });
    queryClient.invalidateQueries({ queryKey: [purchase ? "suppliers" : "customers"] });
  };
  useEffect(() => {
    if (!party.id || party.name) return;
    const known = parties.find((p) => p.id === party.id);
    if (known) setParty({ id: known.id, name: known.name });
  }, [parties, party.id, party.name]);
  const [issueDate, setIssueDate] = useState(initial?.issue_date ?? initial?.start_date ?? todayISO());
  const [secondDate, setSecondDate] = useState((dateField && initial?.[dateField]) || "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const quote = kind === "quote";
  const [reference, setReference] = useState(initial?.reference ?? "");
  const [deliveryAddress, setDeliveryAddress] = useState(initial?.delivery_address ?? "");
  const [items, setItems] = useState(() =>
    initial?.items?.length
      ? initial.items.map((item) => ({
          key: nextKey++,
          product_id: item.product_id ?? null,
          description: item.description,
          quantity: String(Number(item.quantity)),
          unit_price: String(Number(item.unit_price)),
          tax_rate: String(Number(item.tax_rate)),
        }))
      : [blankItem()]
  );

  const totals = computeTotals(items);

  function updateItem(key, patch) {
    setItems((prev) => prev.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  }

  // Typing (or picking) a product's name fills in its price and tax.
  function describe(key, description) {
    const product = products.find((p) => p.name.toLowerCase() === description.trim().toLowerCase());
    updateItem(
      key,
      product
        ? { description: product.name, product_id: product.id, unit_price: String(Number(product.unit_price)), tax_rate: String(Number(product.tax_rate)) }
        : { description, product_id: null }
    );
  }

  function loadItems(saved) {
    const loaded = saved.map((item) => ({
      key: nextKey++,
      product_id: item.product_id ?? null,
      description: item.description,
      quantity: String(Number(item.quantity)),
      unit_price: String(Number(item.unit_price)),
      tax_rate: String(Number(item.tax_rate)),
    }));
    setItems((prev) => (prev.every(isBlank) ? loaded : [...prev, ...loaded]));
  }

  function payloadItems() {
    return items.map(({ product_id, description, quantity, unit_price, tax_rate }) => ({
      product_id,
      description,
      quantity,
      unit_price: unit_price || "0",
      tax_rate: tax_rate || "0",
    }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    let partyId = party.id;
    if (!partyId) {
      const name = party.name.trim();
      if (!name) return;
      setAddingParty(true);
      try {
        const { data } = await apiClient.post(purchase ? "/suppliers" : "/customers", { name });
        partyId = data.id;
        setParty({ id: data.id, name: data.name });
        queryClient.invalidateQueries({ queryKey: [purchase ? "suppliers" : "customers"] });
        toast.success(t(`party.added.${purchase ? "supplier" : "customer"}`, { name: data.name }));
      } catch (error) {
        toast.error(errorMessage(error));
        return;
      } finally {
        setAddingParty(false);
      }
    }
    // Remember what was typed: each new item becomes a product, so next
    // time it's suggested with its price and VAT. Never blocks the save.
    let lines = items;
    const known = new Set(products.map((p) => p.name.trim().toLowerCase()));
    const fresh = !purchase && rememberItems ? items.filter((i) => !i.product_id && i.description.trim() && Number(i.unit_price) > 0 && !known.has(i.description.trim().toLowerCase())) : [];
    if (fresh.length) {
      const made = new Map();
      for (const item of fresh) {
        const name = item.description.trim();
        if (made.has(name.toLowerCase())) continue;
        try {
          const { data } = await apiClient.post("/products", { name, unit_price: item.unit_price, tax_rate: item.tax_rate || "0" });
          made.set(name.toLowerCase(), data.id);
        } catch {
          /* e.g. a viewer, or a name clash: the document still saves */
        }
      }
      if (made.size) {
        lines = items.map((i) => (!i.product_id && made.has(i.description.trim().toLowerCase()) ? { ...i, product_id: made.get(i.description.trim().toLowerCase()) } : i));
        setItems(lines);
        queryClient.invalidateQueries({ queryKey: ["products"] });
        toast.success(t("editor.itemsRemembered", { count: made.size }));
      }
    }
    onSubmit({
      [purchase ? "supplier_id" : "customer_id"]: partyId,
      issue_date: issueDate,
      ...(secondDate && { [dateField]: secondDate }),
      notes: notes || null,
      reference: reference.trim() || null,
      ...(quote && { title: title.trim(), description: description.trim() }),
      ...(purchase && { delivery_address: deliveryAddress.trim() || null }),
      items: lines.map(({ product_id, description, quantity, unit_price, tax_rate }) => ({
        product_id,
        description,
        quantity,
        unit_price: unit_price || "0",
        tax_rate: tax_rate || "0",
      })),
    });
  }

  const remove = (key) => setItems((prev) => prev.filter((i) => i.key !== key));

  return (
    <>
    <form onSubmit={handleSubmit} className="space-y-5 pb-24 md:pb-0">
      <section className="card space-y-4 p-4 sm:p-5">
        <Field label={t(purchase ? "editor.supplier" : "editor.customer")}>
          <PartyCombobox
            parties={parties}
            value={party}
            onChange={setParty}
            kind={purchase ? "supplier" : "customer"}
            required
            disabled={lockParty}
            placeholder={t(purchase ? "party.typeSupplier" : "party.typeCustomer")}
            onAddNew={setNewParty}
          />
          {purchase && suppliers.length === 0 && !party.name && (
            <p className="mt-1.5 text-xs text-zinc-500">
              {t("editor.noSuppliers")}{" "}
              <Link to="/purchase-orders?tab=suppliers" className="font-medium text-indigo-600 hover:text-indigo-700">
                {t("editor.addSupplier")}
              </Link>
            </p>
          )}
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label={issueLabel ?? t("editor.issueDate")}>
            <input className="input" type="date" required value={issueDate} onChange={(e) => setIssueDate(e.target.value)} />
          </Field>
          {dateField && (
            <Field label={dateLabel} hint={dateHint}>
              <input className="input" type="date" min={issueDate} value={secondDate} onChange={(e) => setSecondDate(e.target.value)} />
            </Field>
          )}
        </div>
        {children}
        {quote && (
          <>
            <Field label={t("editor.title")} hint={t("editor.titleHint")}>
              <input className="input" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("editor.titlePlaceholder")} />
            </Field>
            <Field label={t("editor.descriptionLabel")} hint={t("editor.descriptionHint")}>
              <textarea className="input" rows={3} maxLength={5000} value={description} onChange={(e) => setDescription(e.target.value)} />
            </Field>
          </>
        )}
        <div>
          <Field label={t("editor.reference")} hint={t("editor.referenceHint")}>
            <input className="input" maxLength={100} value={reference} onChange={(e) => setReference(e.target.value)} placeholder={t("editor.referencePlaceholder")} />
          </Field>
        </div>
      </section>

      {notVatRegistered && items.some((i) => Number(i.tax_rate) > 0) && (
        <p role="status" className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-inset ring-amber-200/70">{t("vat.chargingWarning")}</p>
      )}
      <section className="card p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-zinc-900">{t("document.lineItems")}</h2>
          <SavedItems onLoad={loadItems} currentItems={payloadItems} canSave={items.some((i) => !isBlank(i))} />
        </div>

        <datalist id="product-names">
          {products.map((p) => (
            <option key={p.id} value={p.name}>
              {formatMoney(p.unit_price)}
            </option>
          ))}
        </datalist>

        {wide ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-left text-xs font-medium text-zinc-500">
                  <th className="w-8 pb-2 font-medium">#</th>
                  <th className="pb-2 font-medium">{t("editor.itemColumn")}</th>
                  <th className="w-24 pb-2 pl-2 text-right font-medium">{t("editor.qty")}</th>
                  <th className="w-32 pb-2 pl-2 text-right font-medium">{t("editor.unitPrice")}</th>
                  <th className="w-24 pb-2 pl-2 text-right font-medium">{t("editor.taxPercent")}</th>
                  <th className="w-32 pb-2 pl-2 text-right font-medium">{t("editor.amount")}</th>
                  <th className="w-10 pb-2" aria-label={t("editor.remove")} />
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => (
                  <tr key={item.key} className="border-b border-zinc-100 align-top last:border-0">
                    <td className="py-2.5 pt-[18px] text-xs tabular-nums text-zinc-400">{index + 1}</td>
                    <td className="py-2">
                      <input
                        className="input"
                        list="product-names"
                        aria-label={t("editor.description")}
                        placeholder={t("editor.itemPlaceholder")}
                        required
                        value={item.description}
                        onChange={(e) => describe(item.key, e.target.value)}
                      />
                    </td>
                    <td className="py-2 pl-2">
                      <input className="input text-right tabular-nums" aria-label={t("editor.qty")} required {...NUMBER} value={item.quantity} onChange={(e) => updateItem(item.key, { quantity: e.target.value })} />
                    </td>
                    <td className="py-2 pl-2">
                      <input className="input text-right tabular-nums" aria-label={t("editor.unitPrice")} required {...NUMBER} value={item.unit_price} onChange={(e) => updateItem(item.key, { unit_price: e.target.value })} />
                    </td>
                    <td className="py-2 pl-2">
                      <input className="input text-right tabular-nums" aria-label={t("editor.taxPercent")} {...NUMBER} value={item.tax_rate} onChange={(e) => updateItem(item.key, { tax_rate: e.target.value })} />
                    </td>
                    <td className="py-2 pl-2 pt-[18px] text-right font-medium tabular-nums text-zinc-900">{formatMoney(lineCents(item) / 100)}</td>
                    <td className="py-2 pl-1 text-right">
                      {items.length > 1 && (
                        <button
                          type="button"
                          onClick={() => remove(item.key)}
                          aria-label={t("editor.removeLine", { n: index + 1 })}
                          className="pressable mt-1.5 rounded-md p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-red-600"
                        >
                          <svg viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4" aria-hidden="true">
                            <path d="M5.28 4.22a.75.75 0 0 0-1.06 1.06L6.94 8l-2.72 2.72a.75.75 0 1 0 1.06 1.06L8 9.06l2.72 2.72a.75.75 0 1 0 1.06-1.06L9.06 8l2.72-2.72a.75.75 0 0 0-1.06-1.06L8 6.94 5.28 4.22Z" />
                          </svg>
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ol className="space-y-3">
            {items.map((item, index) => (
              <li key={item.key} className="rounded-lg border border-zinc-200/80 bg-zinc-50/50 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-400">{t("editor.item", { n: index + 1 })}</span>
                  <span className="text-sm font-medium tabular-nums text-zinc-900">{formatMoney(lineCents(item) / 100)}</span>
                </div>
                <input
                  className="input"
                  list="product-names"
                  aria-label={t("editor.description")}
                  placeholder={t("editor.itemPlaceholder")}
                  required
                  value={item.description}
                  onChange={(e) => describe(item.key, e.target.value)}
                />
                <div className="mt-2 grid grid-cols-3 gap-2">
                  <Field label={t("editor.qty")}>
                    <input className="input tabular-nums" required {...NUMBER} value={item.quantity} onChange={(e) => updateItem(item.key, { quantity: e.target.value })} />
                  </Field>
                  <Field label={t("editor.unitPrice")}>
                    <input className="input tabular-nums" required {...NUMBER} value={item.unit_price} onChange={(e) => updateItem(item.key, { unit_price: e.target.value })} />
                  </Field>
                  <Field label={t("editor.taxPercent")}>
                    <input className="input tabular-nums" {...NUMBER} value={item.tax_rate} onChange={(e) => updateItem(item.key, { tax_rate: e.target.value })} />
                  </Field>
                </div>
                {items.length > 1 && (
                  <button type="button" onClick={() => remove(item.key)} className="pressable mt-2 rounded-md px-2 py-1 text-sm text-zinc-500 hover:text-red-600">
                    {t("editor.remove")}
                  </button>
                )}
              </li>
            ))}
          </ol>
        )}
        <Button variant="secondary" className="mt-4 w-full" onClick={() => setItems((prev) => [...prev, blankItem()])}>
          {t("editor.addLine")}
        </Button>
        {!purchase && (
          <label className="mt-3 flex items-start gap-2 text-sm text-zinc-600">
            <input type="checkbox" className="mt-0.5 h-4 w-4 rounded border-zinc-300" checked={rememberItems} onChange={(e) => setRememberItems(e.target.checked)} />
            <span>{t("editor.rememberItems")}</span>
          </label>
        )}
      </section>

      <section className="card space-y-4 p-4 sm:p-5">
        {purchase && (
          <Field label={t("editor.deliveryAddress")} hint={t("editor.deliveryAddressHint")}>
            <textarea className="input" rows={2} value={deliveryAddress} onChange={(e) => setDeliveryAddress(e.target.value)} />
          </Field>
        )}
        <Field label={t("editor.notes")} hint={t(purchase ? "editor.notesHintSupplier" : "editor.notesHint")}>
          <textarea className="input" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
        {kind === "invoice" && (
          <p className="text-xs text-zinc-500">
            {t("editor.bankingHint")}{" "}
            <Link to="/settings?tab=documents" className="font-medium text-indigo-600 hover:text-indigo-700">
              {t("editor.bankingLink")}
            </Link>
          </p>
        )}
      </section>

      {/* Totals + submit: pinned above the tab bar on phones so the total is
          always in view while editing items; inline on larger screens. */}
      <div className="fixed inset-x-0 bottom-[var(--tabbar-height)] z-10 border-t border-zinc-200/80 bg-white/90 px-4 py-3 backdrop-blur-md md:static md:rounded-xl md:border md:bg-white md:px-5 md:py-4 md:shadow-card md:backdrop-blur-none">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4">
          <div className="text-sm">
            <p className="text-xs text-zinc-500">
              {t("document.totalExcl")} {formatMoney(totals.subtotal)} · {t("document.vat")} {formatMoney(totals.tax)}
            </p>
            <p className="text-xl font-semibold tracking-tight text-zinc-900">
              <span className="mr-1.5 text-xs font-medium text-zinc-500">{t("document.totalIncl")}</span>
              {formatMoney(totals.total)}
            </p>
          </div>
          <button type="submit" className="btn btn-primary" disabled={isSubmitting || addingParty}>
            {isSubmitting || addingParty ? t("common.saving") : submitLabel}
          </button>
        </div>
      </div>
    </form>
      {purchase ? (
        <SupplierSheet supplier={newParty !== null ? { name: newParty } : null} onClose={() => setNewParty(null)} onSaved={partyAdded} />
      ) : (
        <CustomerFormSheet open={newParty !== null} customer={null} initialName={newParty ?? ""} onClose={() => setNewParty(null)} onSaved={partyAdded} />
      )}
    </>
  );
}

/** Load a saved set of lines, or save the current lines for everyone in the company. */
function SavedItems({ onLoad, currentItems, canSave }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: templates = [] } = useLineTemplates();
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["line-templates"] });

  const save = useMutation({
    mutationFn: () => apiClient.post("/line-templates", { name: name.trim(), items: currentItems() }).then((r) => r.data),
    onSuccess: (template) => {
      refresh();
      toast.success(t("editor.saved", { name: template.name }), { description: t("editor.savedShared") });
      setSaving(false);
      setName("");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: (template) => apiClient.delete(`/line-templates/${template.id}`).then(() => template),
    onSuccess: (template) => {
      refresh();
      toast.success(t("editor.savedDeleted", { name: template.name }));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
      {templates.length > 0 && (
        <select
          className="input !h-9 min-w-0 flex-1 !text-sm sm:w-56 sm:flex-none"
          aria-label={t("editor.loadSaved")}
          value=""
          onChange={(e) => {
            const template = templates.find((x) => x.id === e.target.value);
            if (template) {
              onLoad(template.items);
              toast.success(t("editor.savedLoaded", { name: template.name }));
            }
          }}
        >
          <option value="">{t("editor.loadSaved")}</option>
          {templates.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name} ({x.items.length})
            </option>
          ))}
        </select>
      )}
      <Button variant="secondary" className="!h-9 !text-sm" disabled={!canSave} onClick={() => setSaving((v) => !v)}>
        {t("editor.saveItems")}
      </Button>
      {saving && (
        <div className="w-full space-y-3 rounded-lg bg-zinc-50 p-3 ring-1 ring-inset ring-zinc-200/70">
          <div className="flex flex-wrap gap-2">
            <input
              className="input !h-9 min-w-0 flex-1 !text-sm"
              aria-label={t("editor.saveAsName")}
              placeholder={t("editor.saveAsPlaceholder")}
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  if (name.trim()) save.mutate();
                }
              }}
            />
            <Button className="!h-9 !text-sm" disabled={!name.trim() || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? t("common.saving") : t("common.save")}
            </Button>
          </div>
          <p className="text-xs text-zinc-500">{t("editor.savedHint")}</p>
          {templates.length > 0 && (
            <ul className="flex flex-wrap gap-1.5">
              {templates.map((x) => (
                <li key={x.id} className="inline-flex items-center gap-1 rounded-full bg-white py-0.5 pl-2.5 pr-1 text-xs text-zinc-700 ring-1 ring-inset ring-zinc-200">
                  {x.name}
                  <button
                    type="button"
                    aria-label={t("editor.deleteSaved", { name: x.name })}
                    onClick={() => remove.mutate(x)}
                    className="rounded-full p-0.5 text-zinc-400 hover:bg-zinc-100 hover:text-red-600"
                  >
                    <svg viewBox="0 0 16 16" fill="currentColor" className="h-3.5 w-3.5" aria-hidden="true">
                      <path d="M5.28 4.22a.75.75 0 0 0-1.06 1.06L6.94 8l-2.72 2.72a.75.75 0 1 0 1.06 1.06L8 9.06l2.72 2.72a.75.75 0 1 0 1.06-1.06L9.06 8l2.72-2.72a.75.75 0 0 0-1.06-1.06L8 6.94 5.28 4.22Z" />
                    </svg>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
