import { useMemo, useRef, useState } from "react";
import Papa from "papaparse";
import { useMutation } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { errorMessage } from "../utils/format";
import { Button } from "./ui";

const IMPORTS = {
  customers: ["name", "email", "phone", "billing_address", "tax_number", "notes", "contact_first_name", "contact_last_name", "contact_email", "contact_phone", "contact_job_title"],
  products: ["name", "unit_price", "sku", "tax_rate", "description"],
  deals: ["title", "customer", "value", "stage", "expected_close_date", "industry", "owner_email"],
};
const REQUIRED = { customers: ["name"], products: ["name", "unit_price"], deals: ["title", "customer"] };
const EXPORTS = ["customers", "contacts", "products", "deals", "invoices", "quotes", "payments"];
const MAX_ROWS = 5000;

// Column headings other systems (and people) use for each field.
const SYNONYMS = {
  name: ["name", "company", "company name", "client", "client name", "customer", "customer name", "organisation", "organization", "account name", "product", "product name", "item"],
  email: ["email", "e-mail", "email address", "company email"],
  phone: ["phone", "telephone", "tel", "phone number", "mobile", "cell", "cellphone"],
  billing_address: ["address", "billing address", "street address", "physical address", "postal address"],
  tax_number: ["vat", "vat number", "vat no", "tax number", "tax no", "tax id"],
  notes: ["notes", "note", "comments", "description"],
  contact_first_name: ["first name", "contact first name", "contact name", "contact person", "firstname"],
  contact_last_name: ["last name", "surname", "contact last name", "lastname"],
  contact_email: ["contact email", "person email"],
  contact_phone: ["contact phone", "contact mobile", "direct line"],
  contact_job_title: ["job title", "title", "position", "role"],
  unit_price: ["price", "unit price", "rate", "selling price", "amount", "cost"],
  sku: ["sku", "code", "item code", "product code"],
  tax_rate: ["vat rate", "tax rate", "vat %", "tax %"],
  description: ["description", "details"],
  title: ["deal", "deal name", "title", "opportunity", "opportunity name", "name"],
  customer: ["customer", "client", "company", "account", "organisation", "organization"],
  value: ["value", "amount", "deal value", "size"],
  stage: ["stage", "status", "pipeline stage"],
  expected_close_date: ["close date", "expected close", "expected close date", "closing date"],
  industry: ["industry", "sector"],
  owner_email: ["owner", "owner email", "sales rep", "assigned to"],
};

function guessMapping(entity, headers) {
  const normal = (h) => h.trim().toLowerCase().replace(/[_\s]+/g, " ");
  const used = new Set();
  const mapping = {};
  for (const field of IMPORTS[entity]) {
    const names = [field.replace(/_/g, " "), ...(SYNONYMS[field] ?? [])];
    const match = headers.find((h) => !used.has(h) && names.includes(normal(h)));
    if (match) {
      mapping[field] = match;
      used.add(match);
    }
  }
  return mapping;
}

function downloadCsv(name, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Settings > Import & export. */
export default function DataSettings() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileInput = useRef(null);
  const [entity, setEntity] = useState("customers");
  const [file, setFile] = useState(null); // { name, headers, rows }
  const [mapping, setMapping] = useState({});
  const [update, setUpdate] = useState(false);
  const [result, setResult] = useState(null);
  const missing = REQUIRED[entity].filter((f) => !mapping[f]);

  const mapped = useMemo(
    () =>
      file
        ? file.rows.map((row) => Object.fromEntries(Object.entries(mapping).filter(([, h]) => h).map(([field, header]) => [field, row[header] ?? ""])))
        : [],
    [file, mapping]
  );

  const run = useMutation({
    mutationFn: () => apiClient.post(`/imports/${entity}`, { rows: mapped, update_existing: update }).then((r) => r.data),
    onSuccess: (data) => {
      setResult(data);
      queryClient.invalidateQueries();
      toast.success(t("data.done", { created: data.created, updated: data.updated }));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const exportOne = useMutation({
    mutationFn: (what) => apiClient.get(`/exports/${what}`, { responseType: "text" }).then((r) => ({ what, text: r.data })),
    onSuccess: ({ what, text }) => downloadCsv(`ygt-${what}-${new Date().toISOString().slice(0, 10)}.csv`, text),
    onError: (error) => toast.error(errorMessage(error)),
  });

  function readFile(chosen) {
    if (!chosen) return;
    Papa.parse(chosen, {
      header: true,
      skipEmptyLines: "greedy",
      transformHeader: (h) => h.replace(/^﻿/, "").trim(),
      complete: ({ data, meta, errors }) => {
        if (!meta.fields?.length) {
          toast.error(t("data.unreadable"));
          return;
        }
        if (data.length > MAX_ROWS) toast.warning(t("data.tooMany", { max: MAX_ROWS }));
        setFile({ name: chosen.name, headers: meta.fields.filter(Boolean), rows: data.slice(0, MAX_ROWS), problems: errors.length });
        setMapping(guessMapping(entity, meta.fields));
        setResult(null);
      },
    });
  }

  function template() {
    downloadCsv(`ygt-${entity}-template.csv`, "﻿" + Papa.unparse([IMPORTS[entity], IMPORTS[entity].map(() => "")]));
  }

  const reset = () => {
    setFile(null);
    setMapping({});
    setResult(null);
    if (fileInput.current) fileInput.current.value = "";
  };

  return (
    <div className="space-y-5">
      <section className="card space-y-5 p-4 sm:p-6">
        <div>
          <h2 className="text-base font-semibold text-zinc-900">{t("data.importTitle")}</h2>
          <p className="mt-0.5 text-sm text-zinc-500">{t("data.importIntro")}</p>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="label">{t("data.what")}</span>
            <select
              className="input"
              value={entity}
              onChange={(e) => {
                setEntity(e.target.value);
                if (file) setMapping(guessMapping(e.target.value, file.headers));
                setResult(null);
              }}
            >
              {Object.keys(IMPORTS).map((k) => (
                <option key={k} value={k}>
                  {t(`data.entities.${k}`)}
                </option>
              ))}
            </select>
          </label>
          <input ref={fileInput} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => readFile(e.target.files?.[0])} />
          <Button onClick={() => fileInput.current?.click()}>{file ? t("data.otherFile") : t("data.chooseFile")}</Button>
          <button type="button" onClick={template} className="text-sm font-medium text-indigo-600 hover:text-indigo-700">
            {t("data.template")}
          </button>
        </div>
        <p className="text-xs text-zinc-500">{t("data.excelHint")}</p>

        {file && (
          <>
            <div className="rounded-xl bg-zinc-50 p-4 ring-1 ring-inset ring-zinc-200/70">
              <p className="text-sm font-medium text-zinc-900">{t("data.fileSummary", { name: file.name, count: file.rows.length })}</p>
              <p className="mt-0.5 text-sm text-zinc-500">{t("data.matchIntro")}</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {IMPORTS[entity].map((field) => (
                  <label key={field} className="flex items-center gap-3 text-sm">
                    <span className="w-40 shrink-0 text-zinc-700">
                      {t(`data.fields.${field}`)}
                      {REQUIRED[entity].includes(field) && <span className="text-rose-600"> *</span>}
                    </span>
                    <select className="input !h-9 !py-0 !text-sm" value={mapping[field] ?? ""} onChange={(e) => setMapping((m) => ({ ...m, [field]: e.target.value }))}>
                      <option value="">{t("data.skip")}</option>
                      {file.headers.map((h) => (
                        <option key={h} value={h}>
                          {h}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            </div>

            <div className="overflow-x-auto rounded-xl ring-1 ring-zinc-200">
              <table className="w-full text-sm">
                <thead className="table-head">
                  <tr>
                    {IMPORTS[entity].filter((f) => mapping[f]).map((f) => (
                      <th key={f}>{t(`data.fields.${f}`)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {mapped.slice(0, 5).map((row, i) => (
                    <tr key={i}>
                      {IMPORTS[entity].filter((f) => mapping[f]).map((f) => (
                        <td key={f} className="max-w-[14rem] truncate px-4 py-2 text-zinc-700">
                          {row[f]}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="border-t border-zinc-100 px-4 py-2 text-xs text-zinc-500">{t("data.previewNote", { count: Math.min(5, mapped.length), total: mapped.length })}</p>
            </div>

            <label className="flex items-center gap-3 text-sm text-zinc-700">
              <input type="checkbox" className="h-4 w-4 rounded border-zinc-300" checked={update} onChange={(e) => setUpdate(e.target.checked)} />
              {t("data.updateExisting")}
            </label>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 pt-4">
              <p className={`text-sm ${missing.length ? "text-rose-600" : "text-zinc-500"}`}>
                {missing.length ? t("data.needs", { fields: missing.map((f) => t(`data.fields.${f}`)).join(", ") }) : t("data.ready", { count: mapped.length })}
              </p>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={reset}>
                  {t("common.cancel")}
                </Button>
                <Button onClick={() => run.mutate()} disabled={missing.length > 0 || !mapped.length || run.isPending}>
                  {run.isPending ? t("data.importing") : t("data.import", { count: mapped.length })}
                </Button>
              </div>
            </div>
          </>
        )}

        {result && (
          <div className="rounded-xl bg-white p-4 ring-1 ring-inset ring-zinc-200" role="status">
            <div className="grid grid-cols-3 gap-3 text-center">
              {[
                ["created", "text-emerald-700"],
                ["updated", "text-indigo-700"],
                ["skipped", "text-zinc-600"],
              ].map(([key, tone]) => (
                <div key={key} className="rounded-lg bg-zinc-50 py-3">
                  <p className={`text-2xl font-semibold tabular-nums ${tone}`}>{result[key]}</p>
                  <p className="text-xs text-zinc-500">{t(`data.results.${key}`)}</p>
                </div>
              ))}
            </div>
            {result.errors.length > 0 && (
              <div className="mt-4">
                <p className="text-sm font-medium text-rose-700">{t("data.errors", { count: result.errors.length })}</p>
                <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-sm text-zinc-700">
                  {result.errors.map((e) => (
                    <li key={`${e.row}-${e.message}`}>
                      <span className="font-medium tabular-nums">{t("data.row", { row: e.row })}</span> {e.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="card p-4 sm:p-6">
        <h2 className="text-base font-semibold text-zinc-900">{t("data.exportTitle")}</h2>
        <p className="mt-0.5 text-sm text-zinc-500">{t("data.exportIntro")}</p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {EXPORTS.map((what) => (
            <Button key={what} variant="secondary" onClick={() => exportOne.mutate(what)} disabled={exportOne.isPending && exportOne.variables === what}>
              {t(`data.exports.${what}`)}
            </Button>
          ))}
        </div>
      </section>
    </div>
  );
}
