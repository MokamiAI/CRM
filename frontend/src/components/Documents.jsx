import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useCompany, useCustomers } from "../hooks/useApi";
import { errorMessage } from "../utils/format";
import { Avatar, Button, Field } from "./ui";

// The page width the printable documents are designed at (A4 at 96dpi).
const PAGE_W = 820;
const PAGE_H = 1160;

/** A printable document (HTML from the API) shown at the width of its box. */
function ScaledFrame({ html, frameRef, title }) {
  const box = useRef(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    if (!box.current) return undefined;
    const observer = new ResizeObserver(([entry]) => setScale(Math.min(1, entry.contentRect.width / PAGE_W)));
    observer.observe(box.current);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={box} className="w-full overflow-hidden" style={{ height: PAGE_H * scale }}>
      <iframe
        ref={frameRef}
        title={title}
        srcDoc={html}
        className="origin-top-left border-0 bg-transparent"
        style={{ width: PAGE_W, height: PAGE_H, transform: `scale(${scale})` }}
      />
    </div>
  );
}

/** Full-screen view of an invoice, quote or statement, with Print / Save as PDF. */
export function DocumentViewer({ open, onClose, url, title }) {
  const { t } = useTranslation();
  const frame = useRef(null);
  const { data: html, isLoading, isError } = useQuery({
    queryKey: ["document", url],
    queryFn: () => apiClient.get(url, { responseType: "text" }).then((r) => r.data),
    enabled: open && Boolean(url),
  });
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  // Rendered at the top of the page so it covers the sidebar and tab bar too.
  return createPortal(
    <div className="fixed inset-0 z-[80] flex flex-col bg-zinc-900/50 backdrop-blur-sm md:p-6" role="dialog" aria-modal="true" aria-label={title}>
      <div className="doc-viewer mx-auto flex h-full w-full max-w-5xl flex-col overflow-hidden bg-zinc-100 md:rounded-2xl">
        <header className="safe-top flex items-center gap-3 border-b border-zinc-200 bg-white px-4 py-3">
          <h2 className="min-w-0 flex-1 truncate font-semibold text-zinc-900">{title}</h2>
          <Button onClick={() => frame.current?.contentWindow?.print()} disabled={!html}>
            {t("documents.print")}
          </Button>
          <button type="button" onClick={onClose} className="pressable rounded-lg p-2 text-zinc-500 hover:bg-zinc-100" aria-label={t("common.close")}>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-4 w-4" aria-hidden="true">
              <path d="m4 4 8 8M12 4l-8 8" strokeLinecap="round" />
            </svg>
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-3 sm:p-6">
          {isLoading && <p className="p-8 text-center text-sm text-zinc-500">{t("documents.loading")}</p>}
          {isError && <p className="p-8 text-center text-sm text-rose-600">{t("documents.loadFailed")}</p>}
          {html && <ScaledFrame html={html} frameRef={frame} title={title} />}
        </div>
      </div>
    </div>,
    document.body
  );
}

/** Pick a client to filter a list by: type, choose from the matches. */
export function ClientFilter({ value, onChange }) {
  const { t } = useTranslation();
  const { data: customers = [] } = useCustomers();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const selected = customers.find((c) => c.id === value);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (q ? customers.filter((c) => c.name.toLowerCase().includes(q) || (c.email || "").toLowerCase().includes(q)) : customers).slice(0, 8);
  }, [customers, query]);

  if (selected) {
    return (
      <div className="flex min-w-0 items-center gap-2 rounded-xl bg-white px-3 py-2 ring-1 ring-inset ring-zinc-200">
        <Avatar name={selected.name} size="sm" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-900">{selected.name}</span>
        <button type="button" onClick={() => onChange("")} className="pressable rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700" aria-label={t("clientFilter.clear")}>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-4 w-4" aria-hidden="true">
            <path d="m4 4 8 8M12 4l-8 8" strokeLinecap="round" />
          </svg>
        </button>
      </div>
    );
  }
  const choose = (c) => {
    onChange(c.id);
    setQuery("");
    setOpen(false);
  };
  return (
    <div className="relative">
      <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400">
        <path fillRule="evenodd" d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.45 4.39l3.08 3.08a.75.75 0 1 1-1.06 1.06l-3.08-3.08A7 7 0 0 1 2 9Z" clipRule="evenodd" />
      </svg>
      <input
        type="search"
        role="combobox"
        aria-expanded={open}
        aria-controls="client-filter-list"
        aria-autocomplete="list"
        className="input pl-9"
        placeholder={t("clientFilter.placeholder")}
        value={query}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setActive((i) => Math.min(i + 1, matches.length - 1));
          else if (e.key === "ArrowUp") setActive((i) => Math.max(i - 1, 0));
          else if (e.key === "Enter" && matches[active]) {
            e.preventDefault();
            choose(matches[active]);
          } else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && (
        <ul id="client-filter-list" role="listbox" className="absolute inset-x-0 top-full z-30 mt-1 max-h-72 overflow-y-auto rounded-xl bg-white p-1 shadow-pop ring-1 ring-zinc-200">
          {matches.length === 0 ? (
            <li className="px-3 py-2 text-sm text-zinc-500">{t("clientFilter.none")}</li>
          ) : (
            matches.map((c, i) => (
              <li key={c.id} role="option" aria-selected={i === active}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(c)}
                  onMouseEnter={() => setActive(i)}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm ${i === active ? "bg-zinc-100" : ""}`}
                >
                  <Avatar name={c.name} size="sm" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-zinc-900">{c.name}</span>
                    {c.email && <span className="block truncate text-xs text-zinc-500">{c.email}</span>}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

const ACCENTS = ["#4f46e5", "#7c3aed", "#0f766e", "#0369a1", "#15803d", "#b45309", "#be123c", "#18181b"];
const LAYOUTS = ["modern", "classic", "minimal"];
const TEXT_FIELDS = {
  titles: ["invoice_title", "quote_title", "statement_title", "tax_label"],
  bank: ["bank_name", "account_holder", "account_number", "account_type", "branch_name", "branch_code", "swift_code"],
};

/** Upload or remove the logo printed on documents and emails. */
export function LogoUpload({ onChanged = () => {} }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: company } = useCompany();
  const input = useRef(null);
  const done = (message) => (saved) => {
    queryClient.invalidateQueries({ queryKey: ["company"] });
    queryClient.invalidateQueries({ queryKey: ["settings"] });
    queryClient.removeQueries({ queryKey: ["document"] });
    onChanged(saved);
    toast.success(message);
  };
  const upload = useMutation({
    mutationFn: (file) => {
      const body = new FormData();
      body.append("file", file);
      return apiClient.post("/settings/logo", body).then((r) => r.data);
    },
    onSuccess: done(t("documents.logoUploaded")),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: () => apiClient.delete("/settings/logo").then((r) => r.data),
    onSuccess: done(t("documents.logoRemoved")),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const logo = company?.logo_url;
  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="flex h-16 w-40 items-center justify-center overflow-hidden rounded-xl border border-dashed border-slate-300 bg-slate-50">
        {logo ? <img src={logo} alt={t("documents.logoAlt")} className="max-h-14 max-w-[9rem] object-contain" /> : <span className="text-xs text-slate-400">{t("documents.noLogo")}</span>}
      </div>
      <div className="space-y-1.5">
        <div className="flex flex-wrap gap-2">
          <input
            ref={input}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            tabIndex={-1}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              if (file.size > 500 * 1024) return toast.error(t("documents.logoTooBig"));
              upload.mutate(file);
            }}
          />
          <Button variant="secondary" disabled={upload.isPending} onClick={() => input.current?.click()}>
            {upload.isPending ? t("common.saving") : logo ? t("documents.replaceLogo") : t("documents.uploadLogo")}
          </Button>
          {logo && (
            <Button variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate()}>
              {t("documents.removeLogo")}
            </Button>
          )}
        </div>
        <p className="text-xs text-slate-500">{t("documents.logoRules")}</p>
      </div>
    </div>
  );
}

/** Little drawing of each layout for the picker. */
function LayoutArt({ layout, accent }) {
  return (
    <svg viewBox="0 0 60 76" className="h-16 w-auto" aria-hidden="true">
      <rect x="0.5" y="0.5" width="59" height="75" rx="3" fill="#fff" stroke="#e4e4e7" />
      {layout === "modern" && <rect x="0.5" y="0.5" width="59" height="4" rx="2" fill={accent} />}
      <rect x="6" y="10" width="18" height="4" rx="1" fill={layout === "minimal" ? "#18181b" : accent} opacity={layout === "classic" ? 0.85 : 1} />
      <rect x="38" y="10" width="16" height="3" rx="1" fill="#d4d4d8" />
      <rect x="6" y="22" width="22" height="2" rx="1" fill="#d4d4d8" />
      <rect x="6" y="26" width="16" height="2" rx="1" fill="#e4e4e7" />
      {layout === "classic" ? (
        <rect x="6" y="36" width="48" height="5" fill={accent} />
      ) : layout === "modern" ? (
        <rect x="6" y="36" width="48" height="5" rx="1" fill={accent} opacity="0.15" />
      ) : (
        <rect x="6" y="40" width="48" height="0.8" fill="#18181b" />
      )}
      {[45, 51, 57].map((y) => (
        <rect key={y} x="6" y={y} width="48" height="1.6" rx="0.8" fill="#e4e4e7" />
      ))}
      <rect x="36" y="64" width="18" height={layout === "minimal" ? 1 : 3} rx="1" fill={accent} />
    </svg>
  );
}

/** Settings > Documents: how invoices, quotes and statements look, with a
 *  live preview of the unsaved choices. */
export function DocumentTemplateSettings() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [logoVersion, setLogoVersion] = useState(0);
  const { data: saved } = useQuery({ queryKey: ["document-template"], queryFn: () => apiClient.get("/settings/documents").then((r) => r.data) });
  const [form, setForm] = useState(null);
  const [kind, setKind] = useState("invoice");
  const [html, setHtml] = useState("");
  const frame = useRef(null);

  useEffect(() => {
    if (saved && !form) setForm(saved);
  }, [saved, form]);
  const set = (field) => (value) => setForm((prev) => ({ ...prev, [field]: value }));
  const dirty = form && saved && JSON.stringify(form) !== JSON.stringify(saved);
  const valid = form && /^#[0-9a-f]{6}$/i.test(form.accent) && TEXT_FIELDS.titles.every((f) => form[f]?.trim());

  // Live preview: the unsaved template on sample records, a moment after typing stops.
  useEffect(() => {
    if (!form || !valid) return undefined;
    const timer = setTimeout(() => {
      apiClient
        .post("/settings/documents/preview", { template: form, kind }, { responseType: "text" })
        .then((r) => setHtml(r.data))
        .catch(() => {});
    }, 300);
    return () => clearTimeout(timer);
  }, [form, kind, valid, logoVersion]);

  const save = useMutation({
    mutationFn: (body) => apiClient.put("/settings/documents", body).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.setQueryData(["document-template"], data);
      setForm(data);
      queryClient.removeQueries({ queryKey: ["document"] });
      toast.success(t("documents.saved"));
    },
    onError: (error) => toast.error(errorMessage(error, t("documents.saveFailed"))),
  });

  if (!form) return <div className="card h-64 animate-pulse" />;

  const text = (field, { multiline = false, label, placeholder } = {}) => (
    <Field label={label ?? t(`documents.fields.${field}`)} key={field}>
      {multiline ? (
        <textarea className="input min-h-[5rem]" rows={3} value={form[field] ?? ""} placeholder={placeholder} onChange={(e) => set(field)(e.target.value)} />
      ) : (
        <input className="input" value={form[field] ?? ""} placeholder={placeholder} onChange={(e) => set(field)(e.target.value)} />
      )}
    </Field>
  );
  const toggle = (field) => (
    <label className="flex items-center gap-3 text-sm text-zinc-700">
      <input type="checkbox" className="h-4 w-4 rounded border-zinc-300 text-indigo-600" checked={Boolean(form[field])} onChange={(e) => set(field)(e.target.checked)} />
      {t(`documents.fields.${field}`)}
    </label>
  );

  return (
    <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <form
        className="space-y-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) save.mutate(form);
        }}
      >
        <section className="card space-y-4 p-4 sm:p-6">
          <div>
            <h2 className="text-base font-semibold text-zinc-900">{t("documents.look")}</h2>
            <p className="mt-0.5 text-sm text-zinc-500">{t("documents.intro")}</p>
          </div>
          <div role="radiogroup" aria-label={t("documents.layout")} className="grid grid-cols-3 gap-3">
            {LAYOUTS.map((layout) => (
              <button
                key={layout}
                type="button"
                role="radio"
                aria-checked={form.layout === layout}
                onClick={() => set("layout")(layout)}
                className={`flex flex-col items-center gap-2 rounded-xl p-3 text-sm font-medium ring-1 ring-inset transition-colors duration-150 ${
                  form.layout === layout ? "bg-indigo-50/60 text-zinc-900 ring-2 ring-indigo-500" : "text-zinc-600 ring-zinc-200 hover:bg-zinc-50"
                }`}
              >
                <LayoutArt layout={layout} accent={form.accent} />
                {t(`documents.layouts.${layout}`)}
              </button>
            ))}
          </div>
          <div>
            <span className="label">{t("documents.accent")}</span>
            <div className="flex flex-wrap items-center gap-2">
              {ACCENTS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => set("accent")(c)}
                  className={`h-8 w-8 rounded-full ring-offset-2 transition-shadow duration-150 ${form.accent.toLowerCase() === c ? "ring-2 ring-zinc-900" : ""}`}
                  style={{ background: c }}
                  aria-label={c}
                  aria-pressed={form.accent.toLowerCase() === c}
                />
              ))}
              <label className="flex items-center gap-2 rounded-full py-1 pl-1 pr-3 text-sm text-zinc-600 ring-1 ring-inset ring-zinc-200">
                <input type="color" value={form.accent} onChange={(e) => set("accent")(e.target.value)} className="h-6 w-6 cursor-pointer rounded-full border-0 bg-transparent p-0" />
                {t("documents.customColour")}
              </label>
            </div>
          </div>
          <LogoUpload onChanged={() => setLogoVersion((v) => v + 1)} />
          {toggle("show_logo")}
        </section>

        <section className="card space-y-4 p-4 sm:p-6">
          <h2 className="text-base font-semibold text-zinc-900">{t("documents.titles")}</h2>
          <div className="grid gap-4 sm:grid-cols-2">{TEXT_FIELDS.titles.map((f) => text(f))}</div>
          <p className="text-xs text-zinc-500">{t("documents.taxLabelHint", { label: form.tax_label })}</p>
          {text("registration_number", { placeholder: "2019/123456/07" })}
          <div className="grid gap-4 sm:grid-cols-2">
            {text("phone", { placeholder: "011 555 0100" })}
            {text("website", { placeholder: "www.yourcompany.co.za" })}
          </div>
          {toggle("show_customer_tax_number")}
        </section>

        <section className="card space-y-4 p-4 sm:p-6">
          <div>
            <h2 className="text-base font-semibold text-zinc-900">{t("documents.bank")}</h2>
            <p className="mt-0.5 text-sm text-zinc-500">{t("documents.bankHint")}</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">{TEXT_FIELDS.bank.map((f) => text(f))}</div>
          {text("payment_reference")}
        </section>

        <section className="card space-y-4 p-4 sm:p-6">
          <h2 className="text-base font-semibold text-zinc-900">{t("documents.terms")}</h2>
          {text("invoice_terms", { multiline: true, placeholder: t("documents.invoiceTermsPlaceholder") })}
          {text("quote_terms", { multiline: true, placeholder: t("documents.quoteTermsPlaceholder") })}
          {text("footer", { multiline: true })}
        </section>

        <div className="sticky bottom-[calc(var(--tabbar-height)+0.75rem)] z-10 flex items-center justify-end gap-3 rounded-xl bg-white/90 p-3 shadow-pop ring-1 ring-zinc-200 backdrop-blur md:bottom-4">
          {dirty && <span className="mr-auto text-sm text-amber-700">{t("documents.unsaved")}</span>}
          {dirty && (
            <Button variant="secondary" onClick={() => setForm(saved)}>
              {t("common.cancel")}
            </Button>
          )}
          <Button type="submit" disabled={!dirty || !valid || save.isPending}>
            {save.isPending ? t("common.saving") : t("documents.save")}
          </Button>
        </div>
      </form>

      <section className="space-y-3 xl:sticky xl:top-6" aria-label={t("documents.preview")}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-zinc-900">{t("documents.preview")}</h2>
          <div className="inline-flex rounded-xl bg-zinc-100 p-1 text-sm" role="radiogroup">
            {["invoice", "quote", "statement"].map((k) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={kind === k}
                onClick={() => setKind(k)}
                className={`rounded-lg px-3 py-1.5 font-medium transition-colors duration-150 ${kind === k ? "bg-white text-zinc-900 shadow-sm" : "text-zinc-500 hover:text-zinc-700"}`}
              >
                {t(`documents.kinds.${k}`)}
              </button>
            ))}
          </div>
        </div>
        <div className="rounded-2xl bg-zinc-100 p-3 ring-1 ring-inset ring-zinc-200/70">
          {html ? <ScaledFrame html={html} frameRef={frame} title={t("documents.preview")} /> : <div className="aspect-[820/1160] animate-pulse rounded-lg bg-white" />}
        </div>
        <p className="text-xs text-zinc-500">{t("documents.sample")}</p>
      </section>
    </div>
  );
}
