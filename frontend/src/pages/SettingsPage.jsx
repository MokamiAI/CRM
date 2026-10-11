import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import apiClient from "../services/apiClient";
import CustomFieldsManager from "../components/CustomFieldsManager";
import BillingSettings, { PlanNotice } from "../components/Billing";
import { DocumentTemplateSettings } from "../components/Documents";
import DataSettings from "../components/DataSettings";
import { SignatureEditor } from "../components/Signature";
import TeamManager from "../components/TeamManager";
import { ConnectionCard, MAIL_PRESETS } from "../components/ChannelSettings";
import { ErrorState, FilterChips, ListSkeleton, PageHeader } from "../components/ui";
import { errorMessage } from "../utils/format";

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
  customer_term: "customer",
  email_signature: "",
  reminders_enabled: true,
  reminder_offsets: [-3, 0, 7, 14],
};

// Days relative to the due date, offered as toggles. Any other value saved
// through the API still shows (and can be switched off) below.
const REMINDER_PRESETS = [-7, -3, -1, 0, 1, 3, 7, 14, 30];

function describeOffset(days) {
  if (days === 0) return i18n.t("settings.reminders.onDue");
  return i18n.t(days < 0 ? "settings.reminders.before" : "settings.reminders.after", { count: Math.abs(days) });
}

function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-zinc-500">{hint}</span>}
    </label>
  );
}

// text-base (16px), not text-sm, so focusing an input doesn't trigger
// iOS Safari/webview's auto-zoom-on-focus for fields under 16px.
const inputClass = "input";

const TABS = ["general", "team", "billing", "documents", "email", "whatsapp", "sms", "fields", "data"];
const WHATSAPP_STEPS = ["app", "ids", "token", "save", "webhook", "window"];
const SMS_STEPS = ["account", "keys", "sender", "webhook"];

export default function SettingsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiClient.get("/settings").then((res) => res.data),
  });

  const [form, setForm] = useState(EMPTY_FORM);
  const [params, setParams] = useSearchParams();
  const tab = TABS.includes(params.get("tab")) ? params.get("tab") : "general";
  const setTab = (value) => setParams(value === "general" ? {} : { tab: value });
  const [preset, setPreset] = useState("");
  // Picking "Gmail" etc. fills the outgoing server here and the incoming
  // mailbox below; the person only adds their email and app password.
  function applyPreset(name) {
    setPreset(name);
    const p = MAIL_PRESETS[name];
    if (p) setForm((prev) => ({ ...prev, smtp_host: p.smtp_host, smtp_port: p.smtp_port, smtp_use_tls: p.smtp_use_tls }));
  }

  useEffect(() => {
    if (!data) return;
    setForm({
      ...EMPTY_FORM,
      ...data,
      smtp_password: "",
      smtp_port: data.smtp_port ?? "",
      email_signature: data.email_signature ?? "",
    });
  }, [data]);

  const mutation = useMutation({
    mutationFn: (payload) => apiClient.patch("/settings", payload).then((res) => res.data),
    onSuccess: (updated) => {
      queryClient.setQueryData(["settings"], updated);
      queryClient.invalidateQueries({ queryKey: ["company"] });
      toast.success(t("settings.saved"));
    },
    onError: (error) => toast.error(errorMessage(error, t("settings.saveFailed"))),
  });

  const testEmail = useMutation({
    mutationFn: () => apiClient.post("/settings/test-email", {}).then((res) => res.data),
    onSuccess: (result) => toast.success(t("settings.email.testSent"), { description: result.sent_to }),
    onError: (error) => toast.error(t("settings.email.testFailed"), { description: errorMessage(error) }),
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

  if (isLoading) return <ListSkeleton rows={3} />;
  if (isError) return <ErrorState message={t("settings.loadFailed")} />;

  return (
    <div className="max-w-3xl space-y-5">
      <PageHeader title={t("nav.settings")} />
      <FilterChips value={tab} onChange={setTab} options={TABS.map((v) => ({ value: v, label: t(`settings.tabs.${v}`) }))} />
      {(tab === "general" || tab === "email") && (
      <form onSubmit={handleSubmit} className="space-y-5">
        {tab === "general" && (
        <section className="card p-4 sm:p-6">
          <h2 className="mb-4 text-base font-semibold text-zinc-900">{t("settings.company.title")}</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label={t("settings.company.name")}>
              <input
                className={inputClass}
                value={form.company_name}
                onChange={(e) => update("company_name", e.target.value)}
                required
              />
            </Field>
            <Field label={t("customerForm.taxNumber")}>
              <input
                className={inputClass}
                value={form.tax_number ?? ""}
                onChange={(e) => update("tax_number", e.target.value)}
              />
            </Field>
            <Field label={t("settings.company.address")} hint={t("settings.company.addressHint")}>
              <textarea
                className={inputClass}
                rows={2}
                value={form.address ?? ""}
                onChange={(e) => update("address", e.target.value)}
              />
            </Field>
            <Field label={t("settings.company.logo")}>
              <input
                className={inputClass}
                value={form.logo_url ?? ""}
                onChange={(e) => update("logo_url", e.target.value)}
              />
            </Field>
            <Field label={t("settings.company.currency")}>
              <input
                className={inputClass}
                value={form.default_currency}
                onChange={(e) => update("default_currency", e.target.value)}
                maxLength={10}
                required
              />
            </Field>
            <Field label={t("settings.company.timezone")}>
              <input
                className={inputClass}
                value={form.default_timezone}
                onChange={(e) => update("default_timezone", e.target.value)}
                required
              />
            </Field>
          </div>
        </section>
        )}

        {tab === "general" && (
        <section className="card p-4 sm:p-6">
          <h2 className="mb-1 text-base font-semibold text-zinc-900">{t("settings.wording.title")}</h2>
          <p className="mb-4 text-sm text-zinc-500">{t("settings.wording.intro")}</p>
          <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label={t("settings.wording.title")}>
            {["customer", "client"].map((term) => {
              const active = form.customer_term === term;
              return (
                <button
                  key={term}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => update("customer_term", term)}
                  className={`pressable rounded-lg px-4 py-3 text-left transition-colors duration-150 ${
                    active ? "bg-indigo-50 ring-2 ring-indigo-500" : "bg-white ring-1 ring-zinc-200 hover:bg-zinc-50"
                  }`}
                >
                  {/* Raw labels: the wording post-processor must not rewrite the choice itself. */}
                  <span className="block font-medium text-zinc-900">{t(`settings.wording.${term}`, { postProcess: [] })}</span>
                  <span className="mt-0.5 block text-xs text-zinc-500">{t(`settings.wording.${term}Example`, { postProcess: [] })}</span>
                </button>
              );
            })}
          </div>
        </section>
        )}

        {tab === "general" && (
        <section className="card p-4 sm:p-6">
          <h2 className="mb-4 text-base font-semibold text-zinc-900">{t("settings.documents.title")}</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label={t("settings.documents.quotePrefix")}>
              <input
                className={inputClass}
                value={form.quote_prefix}
                onChange={(e) => update("quote_prefix", e.target.value)}
                required
              />
            </Field>
            <Field label={t("settings.documents.invoicePrefix")}>
              <input
                className={inputClass}
                value={form.invoice_prefix}
                onChange={(e) => update("invoice_prefix", e.target.value)}
                required
              />
            </Field>
            <Field label={t("settings.documents.terms")} hint={t("settings.documents.termsHint")}>
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
        )}

        {tab === "email" && (
          <>
        <section className="card p-4 sm:p-6">
          <h2 className="mb-1 text-base font-semibold text-zinc-900">{t("channels.emailPresetTitle")}</h2>
          <p className="mb-3 text-sm text-zinc-500">{t("channels.emailPresetIntro")}</p>
          <select className="input" value={preset} onChange={(e) => applyPreset(e.target.value)} aria-label={t("channels.emailPresetTitle")}>
            <option value="">{t("channels.presets.other")}</option>
            {Object.keys(MAIL_PRESETS).map((p) => (
              <option key={p} value={p}>
                {t(`channels.presets.${p}`)}
              </option>
            ))}
          </select>
          {(preset === "gmail" || preset === "microsoft" || preset === "yahoo") && (
            <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-[13px] text-amber-800">{t(`channels.appPassword.${preset}`)}</p>
          )}
        </section>
        <section className="card p-4 sm:p-6">
          <h2 className="mb-1 text-base font-semibold text-zinc-900">{t("settings.email.title")}</h2>
          <p className="mb-4 text-sm text-zinc-500">{t("settings.email.intro")}</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label={t("settings.email.senderName")} hint={t("settings.email.senderNameHint")}>
              <input
                className={inputClass}
                value={form.sender_name ?? ""}
                onChange={(e) => update("sender_name", e.target.value)}
              />
            </Field>
            <Field label={t("settings.email.senderEmail")} hint={t("settings.email.senderEmailHint")}>
              <input
                type="email"
                className={inputClass}
                value={form.sender_email ?? ""}
                onChange={(e) => update("sender_email", e.target.value)}
              />
            </Field>
            <Field label={t("settings.email.host")}>
              <input
                className={inputClass}
                placeholder="smtp.gmail.com"
                value={form.smtp_host ?? ""}
                onChange={(e) => update("smtp_host", e.target.value)}
              />
            </Field>
            <Field label={t("settings.email.port")}>
              <input
                type="number"
                className={inputClass}
                placeholder="587"
                value={form.smtp_port}
                onChange={(e) => update("smtp_port", e.target.value)}
              />
            </Field>
            <Field label={t("settings.email.username")}>
              <input
                className={inputClass}
                value={form.smtp_username ?? ""}
                onChange={(e) => update("smtp_username", e.target.value)}
              />
            </Field>
            <Field
              label={t("settings.email.password")}
              hint={data?.smtp_password_set ? t("settings.email.passwordSaved") : undefined}
            >
              <input
                type="password"
                className={inputClass}
                placeholder={data?.smtp_password_set ? "••••••••" : ""}
                value={form.smtp_password}
                onChange={(e) => update("smtp_password", e.target.value)}
              />
            </Field>
            <label className="flex items-center gap-2 text-sm text-zinc-700 sm:col-span-2">
              <input
                type="checkbox"
                checked={form.smtp_use_tls}
                onChange={(e) => update("smtp_use_tls", e.target.checked)}
              />
              {t("settings.email.tls")}
            </label>
          </div>
          <div className="mt-6 flex flex-col gap-2 border-t border-zinc-100 pt-4 sm:flex-row sm:items-center sm:gap-4">
            <button
              type="button"
              onClick={() => testEmail.mutate()}
              disabled={testEmail.isPending}
              className="btn btn-secondary"
            >
              {testEmail.isPending ? t("common.sending") : t("settings.email.test")}
            </button>
            <span className="text-sm text-zinc-500">
              {t("settings.email.testHint")}
            </span>
          </div>
        </section>
        <section className="card p-4 sm:p-6">
          <label htmlFor="company-signature" className="mb-1 block text-base font-semibold text-zinc-900">
            {t("signature.company")}
          </label>
          <p className="mb-4 text-sm text-zinc-500">{t("signature.companyHint")}</p>
          <SignatureEditor
            id="company-signature"
            value={form.email_signature}
            onChange={(value) => update("email_signature", value)}
            placeholder={t("signature.companyPlaceholder")}
            fallback={form.company_name}
            greeting={t("signature.greeting")}
          />
        </section>
          </>
        )}

        {tab === "general" && (
        <section className="card p-4 sm:p-6">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-zinc-900">{t("settings.reminders.title")}</h2>
              <p className="mt-1 text-sm text-zinc-500">{t("settings.reminders.intro")}</p>
            </div>
            <label className="flex shrink-0 items-center gap-2 pt-1 text-sm font-medium text-zinc-700">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={form.reminders_enabled}
                onChange={(e) => update("reminders_enabled", e.target.checked)}
              />
              {t("settings.reminders.on")}
            </label>
          </div>
          <fieldset disabled={!form.reminders_enabled} className="disabled:opacity-50">
            <legend className="mb-2 text-sm font-medium text-zinc-700">{t("settings.reminders.legend")}</legend>
            <div className="flex flex-wrap gap-2">
              {[...new Set([...REMINDER_PRESETS, ...form.reminder_offsets])]
                .sort((a, b) => a - b)
                .map((days) => {
                  const active = form.reminder_offsets.includes(days);
                  return (
                    <button
                      key={days}
                      type="button"
                      aria-pressed={active}
                      onClick={() =>
                        update(
                          "reminder_offsets",
                          active
                            ? form.reminder_offsets.filter((d) => d !== days)
                            : [...form.reminder_offsets, days].sort((a, b) => a - b)
                        )
                      }
                      className={`pressable rounded-full px-3 py-1.5 text-sm font-medium transition-colors duration-150 ${
                        active
                          ? "bg-indigo-600 text-white"
                          : "bg-white text-zinc-600 ring-1 ring-zinc-200 hover:bg-zinc-50"
                      }`}
                    >
                      {describeOffset(days)}
                    </button>
                  );
                })}
            </div>
            {form.reminders_enabled && form.reminder_offsets.length === 0 && (
              <p className="mt-2 text-xs text-amber-600">{t("settings.reminders.none")}</p>
            )}
          </fieldset>
        </section>
        )}

        <div className="flex justify-end">
          <button type="submit" disabled={mutation.isPending} className="btn btn-primary">
            {mutation.isPending ? t("common.saving") : t("settings.save")}
          </button>
        </div>
      </form>
      )}
      {tab === "email" && (
        <ConnectionCard
          kind="email_in"
          providers={["imap"]}
          title={t("channels.mailboxTitle")}
          intro={t("channels.mailboxIntro")}
          preset={preset ? { host: MAIL_PRESETS[preset].host, port: MAIL_PRESETS[preset].port, username: form.sender_email || undefined } : null}
        />
      )}
      {(tab === "whatsapp" || tab === "sms") && <PlanNotice feature="whatsapp_sms" />}
      {tab === "whatsapp" && (
        <ConnectionCard
          kind="whatsapp"
          providers={["meta"]}
          title={t("channels.whatsappTitle")}
          intro={t("channels.whatsappIntro")}
          steps={WHATSAPP_STEPS.map((s) => t(`channels.whatsappSteps.${s}`))}
          testWithNumber
        />
      )}
      {tab === "sms" && (
        <ConnectionCard
          kind="sms"
          providers={["bulksms", "clickatell", "twilio"]}
          title={t("channels.smsTitle")}
          intro={t("channels.smsIntro")}
          steps={SMS_STEPS.map((s) => t(`channels.smsSteps.${s}`))}
          testWithNumber
        />
      )}
      {tab === "team" && <TeamManager />}
      {tab === "fields" && <PlanNotice feature="custom_fields" />}
      {tab === "fields" && <CustomFieldsManager />}
      {tab === "billing" && <BillingSettings />}
      {tab === "documents" && <DocumentTemplateSettings />}
      {tab === "data" && <DataSettings />}
    </div>
  );
}
