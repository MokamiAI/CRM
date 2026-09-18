import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "../services/apiClient";

const EMPTY_FORM = {
  company_name: "",
  address: "",
  tax_number: "",
  default_currency: "",
  default_timezone: "",
  logo_url: "",
  invoice_prefix: "",
  quote_prefix: "",
  payment_terms_days: 30,
  sender_name: "",
  sender_email: "",
  smtp_host: "",
  smtp_port: "",
  smtp_username: "",
  smtp_password: "",
  smtp_use_tls: true,
};

function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-gray-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-gray-500">{hint}</span>}
    </label>
  );
}

// text-base (16px), not text-sm, so focusing an input doesn't trigger
// iOS Safari/webview's auto-zoom-on-focus for fields under 16px.
const inputClass =
  "w-full rounded border border-gray-300 px-3 py-2 text-base focus:border-indigo-500 focus:outline-none";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiClient.get("/settings").then((res) => res.data),
  });

  const [form, setForm] = useState(EMPTY_FORM);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!data) return;
    setForm({
      ...EMPTY_FORM,
      ...data,
      smtp_password: "",
      smtp_port: data.smtp_port ?? "",
    });
  }, [data]);

  const mutation = useMutation({
    mutationFn: (payload) => apiClient.patch("/settings", payload).then((res) => res.data),
    onSuccess: (updated) => {
      queryClient.setQueryData(["settings"], updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleSubmit(event) {
    event.preventDefault();
    const payload = { ...form };
    // Don't overwrite a stored SMTP password with an empty field — only
    // send it if the admin actually typed a new one.
    if (!payload.smtp_password) delete payload.smtp_password;
    if (payload.smtp_port === "") payload.smtp_port = null;
    mutation.mutate(payload);
  }

  if (isLoading) return <p className="text-gray-500">Loading settings…</p>;
  if (isError) return <p className="text-red-600">Failed to load settings.</p>;

  return (
    <form onSubmit={handleSubmit} className="max-w-3xl space-y-8">
      <section className="rounded-lg bg-white p-6 shadow-sm ring-1 ring-gray-200">
        <h2 className="mb-4 text-lg font-semibold text-gray-800">Company</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Company name">
            <input
              className={inputClass}
              value={form.company_name}
              onChange={(e) => update("company_name", e.target.value)}
              required
            />
          </Field>
          <Field label="Tax number">
            <input
              className={inputClass}
              value={form.tax_number ?? ""}
              onChange={(e) => update("tax_number", e.target.value)}
            />
          </Field>
          <Field label="Address" hint="Shown on invoice/quote PDFs">
            <textarea
              className={inputClass}
              rows={2}
              value={form.address ?? ""}
              onChange={(e) => update("address", e.target.value)}
            />
          </Field>
          <Field label="Logo URL">
            <input
              className={inputClass}
              value={form.logo_url ?? ""}
              onChange={(e) => update("logo_url", e.target.value)}
            />
          </Field>
          <Field label="Default currency">
            <input
              className={inputClass}
              value={form.default_currency}
              onChange={(e) => update("default_currency", e.target.value)}
              maxLength={10}
              required
            />
          </Field>
          <Field label="Default timezone">
            <input
              className={inputClass}
              value={form.default_timezone}
              onChange={(e) => update("default_timezone", e.target.value)}
              required
            />
          </Field>
        </div>
      </section>

      <section className="rounded-lg bg-white p-6 shadow-sm ring-1 ring-gray-200">
        <h2 className="mb-4 text-lg font-semibold text-gray-800">Quotes & invoices</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Quote number prefix">
            <input
              className={inputClass}
              value={form.quote_prefix}
              onChange={(e) => update("quote_prefix", e.target.value)}
              required
            />
          </Field>
          <Field label="Invoice number prefix">
            <input
              className={inputClass}
              value={form.invoice_prefix}
              onChange={(e) => update("invoice_prefix", e.target.value)}
              required
            />
          </Field>
          <Field label="Payment terms (days)" hint="Default due date = issue date + this many days">
            <input
              type="number"
              min={0}
              max={365}
              className={inputClass}
              value={form.payment_terms_days}
              onChange={(e) => update("payment_terms_days", Number(e.target.value))}
              required
            />
          </Field>
        </div>
      </section>

      <section className="rounded-lg bg-white p-6 shadow-sm ring-1 ring-gray-200">
        <h2 className="mb-1 text-lg font-semibold text-gray-800">Outgoing email</h2>
        <p className="mb-4 text-sm text-gray-500">
          The email address and SMTP account used to send invoices, quotes, and payment
          reminders to customers. Leave the SMTP fields blank to use the server default
          account instead of your own.
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Sender name" hint='e.g. "Acme Billing"'>
            <input
              className={inputClass}
              value={form.sender_name ?? ""}
              onChange={(e) => update("sender_name", e.target.value)}
            />
          </Field>
          <Field label="Sender email" hint="Where customer replies will land">
            <input
              type="email"
              className={inputClass}
              value={form.sender_email ?? ""}
              onChange={(e) => update("sender_email", e.target.value)}
            />
          </Field>
          <Field label="SMTP host">
            <input
              className={inputClass}
              placeholder="smtp.gmail.com"
              value={form.smtp_host ?? ""}
              onChange={(e) => update("smtp_host", e.target.value)}
            />
          </Field>
          <Field label="SMTP port">
            <input
              type="number"
              className={inputClass}
              placeholder="587"
              value={form.smtp_port}
              onChange={(e) => update("smtp_port", e.target.value)}
            />
          </Field>
          <Field label="SMTP username">
            <input
              className={inputClass}
              value={form.smtp_username ?? ""}
              onChange={(e) => update("smtp_username", e.target.value)}
            />
          </Field>
          <Field
            label="SMTP password"
            hint={data?.smtp_password_set ? "A password is already saved — leave blank to keep it." : undefined}
          >
            <input
              type="password"
              className={inputClass}
              placeholder={data?.smtp_password_set ? "••••••••" : ""}
              value={form.smtp_password}
              onChange={(e) => update("smtp_password", e.target.value)}
            />
          </Field>
          <label className="flex items-center gap-2 text-sm text-gray-700 sm:col-span-2">
            <input
              type="checkbox"
              checked={form.smtp_use_tls}
              onChange={(e) => update("smtp_use_tls", e.target.checked)}
            />
            Use TLS
          </label>
        </div>
      </section>

      <div className="flex items-center gap-4">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
        >
          {mutation.isPending ? "Saving…" : "Save settings"}
        </button>
        {saved && <span className="text-sm text-green-600">Saved.</span>}
        {mutation.isError && (
          <span className="text-sm text-red-600">Failed to save settings.</span>
        )}
      </div>
    </form>
  );
}
