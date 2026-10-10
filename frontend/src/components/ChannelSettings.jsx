import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { errorMessage, formatDateTime } from "../utils/format";
import { celebrate } from "../utils/motion";
import { Button } from "./ui";

// What each provider's form asks for. `secret` fields are never shown
// again once saved (the API only says whether one is stored).
export const PROVIDERS = {
  imap: {
    fields: [
      { name: "host", placeholder: "imap.gmail.com" },
      { name: "port", type: "number", placeholder: "993", optional: true },
      { name: "username", type: "email" },
      { name: "password", secret: true },
      { name: "folder", placeholder: "INBOX", optional: true },
    ],
    toggles: [
      { name: "use_ssl", default: true },
      { name: "only_known_customers", default: true },
    ],
  },
  meta: {
    fields: [
      { name: "phone_number_id", placeholder: "109876543210987" },
      { name: "business_account_id", optional: true },
      { name: "access_token", secret: true },
      { name: "app_secret", secret: true, optional: true },
    ],
  },
  bulksms: { fields: [{ name: "token_id" }, { name: "token_secret", secret: true }, { name: "sender", optional: true, placeholder: "MyBusiness" }] },
  clickatell: { fields: [{ name: "api_key", secret: true }, { name: "sender", optional: true }] },
  twilio: { fields: [{ name: "account_sid", placeholder: "AC…" }, { name: "auth_token", secret: true }, { name: "sender", placeholder: "+27…" }] },
};

// Mailbox presets: most people only need to pick their provider.
export const MAIL_PRESETS = {
  gmail: { smtp_host: "smtp.gmail.com", smtp_port: 587, smtp_use_tls: true, host: "imap.gmail.com", port: 993 },
  microsoft: { smtp_host: "smtp.office365.com", smtp_port: 587, smtp_use_tls: true, host: "outlook.office365.com", port: 993 },
  zoho: { smtp_host: "smtp.zoho.com", smtp_port: 587, smtp_use_tls: true, host: "imap.zoho.com", port: 993 },
  yahoo: { smtp_host: "smtp.mail.yahoo.com", smtp_port: 587, smtp_use_tls: true, host: "imap.mail.yahoo.com", port: 993 },
};

export function useConnections() {
  return useQuery({ queryKey: ["connections"], queryFn: () => apiClient.get("/settings/channels").then((r) => r.data) });
}

function StatusPill({ connection, pillRef }) {
  const { t } = useTranslation();
  // Saved but switched off reads as neutral, whatever the last test said.
  const label = connection.status !== "not_set" && !connection.enabled ? "off" : connection.status;
  const tone = {
    ok: "bg-emerald-50 text-emerald-700 ring-emerald-200/70",
    error: "bg-rose-50 text-rose-700 ring-rose-200/70",
    untested: "bg-amber-50 text-amber-700 ring-amber-200/70",
  }[label] ?? "bg-zinc-100 text-zinc-500 ring-zinc-200";
  return (
    // Keyed on the state so a change crossfades (blur bridges old and new).
    <span key={label} ref={pillRef} className={`badge-swap inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${tone}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {t(`channels.status.${label}`)}
    </span>
  );
}

function CopyField({ label, value }) {
  const { t } = useTranslation();
  return (
    <div>
      <span className="label">{label}</span>
      <div className="flex gap-2">
        <input className="input font-mono !text-xs" readOnly value={value} onFocus={(e) => e.target.select()} />
        <Button variant="secondary" onClick={() => navigator.clipboard?.writeText(value).then(() => toast.success(t("channels.copied")))}>
          {t("channels.copy")}
        </Button>
      </div>
    </div>
  );
}

/** One channel's connection form: provider, fields, enable, save, test. */
export function ConnectionCard({ kind, providers, title, intro, steps, preset, testWithNumber = false }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: all = [], isLoading } = useConnections();
  const saved = all.find((c) => c.kind === kind) ?? { kind, status: "not_set", settings: {}, secrets_set: {} };

  const [form, setForm] = useState(null); // null until the saved values load
  const [secrets, setSecrets] = useState({});
  const [testTo, setTestTo] = useState("");
  const pill = useRef(null);
  if (form === null && !isLoading) {
    const provider = saved.provider ?? providers[0];
    setForm({ provider, enabled: saved.enabled ?? false, settings: { ...saved.settings } });
  }
  // A preset (e.g. "Gmail") fills in hosts and ports, never credentials.
  const [lastPreset, setLastPreset] = useState(preset);
  if (preset !== lastPreset) {
    setLastPreset(preset);
    if (preset && form) setForm({ ...form, settings: { ...form.settings, ...preset } });
  }

  const save = useMutation({
    mutationFn: (body) => apiClient.put(`/settings/channels/${kind}`, body).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.setQueryData(["connections"], (prev = []) => [...prev.filter((c) => c.kind !== kind), data]);
      queryClient.invalidateQueries({ queryKey: ["available-channels"] });
      setSecrets({});
      toast.success(t("channels.saved"));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const test = useMutation({
    mutationFn: () => apiClient.post(`/settings/channels/${kind}/test`, { to: testTo || null }).then((r) => r.data),
    onSuccess: (data) => {
      const firstConnect = data.status === "ok" && saved.status !== "ok";
      queryClient.setQueryData(["connections"], (prev = []) => [...prev.filter((c) => c.kind !== kind), data]);
      // Connecting your own WhatsApp/SMS/mailbox is a milestone: the one
      // moment here worth a little celebration. Repeat tests stay quiet.
      if (firstConnect) requestAnimationFrame(() => celebrate(pill.current, { count: 14 }));
      if (data.status === "ok") toast.success(t("channels.testOk"), { description: data.last_error });
      else toast.error(t("channels.testFailed"), { description: data.last_error });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (!form) return <section className="card h-40 animate-pulse p-6" />;
  const spec = PROVIDERS[form.provider];
  const sameProvider = form.provider === saved.provider;
  const setSetting = (name, value) => setForm({ ...form, settings: { ...form.settings, [name]: value } });
  const submit = (enabled = form.enabled) => {
    const settings = Object.fromEntries(Object.entries(form.settings).filter(([, v]) => v !== "" && v !== undefined));
    for (const toggle of spec.toggles ?? []) settings[toggle.name] = form.settings[toggle.name] ?? toggle.default;
    save.mutate({ provider: form.provider, enabled, settings, secrets });
  };

  return (
    <section className="card p-4 sm:p-6">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-zinc-900">{title}</h2>
        <StatusPill connection={saved} pillRef={pill} />
      </div>
      <p className="mb-4 text-sm text-zinc-500">{intro}</p>

      {steps && (
        <ol className="mb-5 list-decimal space-y-1 rounded-lg bg-zinc-50 py-3 pl-8 pr-4 text-[13px] text-zinc-600 ring-1 ring-inset ring-zinc-200/70">
          {steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      )}

      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {providers.length > 1 && (
          <label className="block">
            <span className="label">{t("channels.provider")}</span>
            <select className="input" value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value, settings: {} })}>
              {providers.map((p) => (
                <option key={p} value={p}>
                  {t(`channels.providers.${p}`)}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {spec.fields.map((f) =>
            f.secret ? (
              <label key={f.name} className="block">
                <span className="label">
                  {t(`channels.fields.${f.name}`)}
                  {f.optional && <span className="font-normal text-zinc-400"> · {t("channels.optional")}</span>}
                </span>
                <input
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={secrets[f.name] ?? ""}
                  onChange={(e) => setSecrets({ ...secrets, [f.name]: e.target.value })}
                  placeholder={sameProvider && saved.secrets_set?.[f.name] ? t("channels.secretSaved") : ""}
                />
              </label>
            ) : (
              <label key={f.name} className="block">
                <span className="label">
                  {t(`channels.fields.${f.name}`)}
                  {f.optional && <span className="font-normal text-zinc-400"> · {t("channels.optional")}</span>}
                </span>
                <input
                  className="input"
                  type={f.type ?? "text"}
                  inputMode={f.type === "number" ? "numeric" : undefined}
                  autoCapitalize="none"
                  value={form.settings[f.name] ?? ""}
                  placeholder={f.placeholder}
                  onChange={(e) => setSetting(f.name, f.type === "number" && e.target.value ? Number(e.target.value) : e.target.value)}
                />
              </label>
            )
          )}
        </div>
        {(spec.toggles ?? []).map((toggle) => (
          <label key={toggle.name} className="flex items-start gap-2.5 text-sm text-zinc-700">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4"
              checked={form.settings[toggle.name] ?? toggle.default}
              onChange={(e) => setSetting(toggle.name, e.target.checked)}
            />
            <span>
              {t(`channels.fields.${toggle.name}`)}
              <span className="block text-xs text-zinc-500">{t(`channels.hints.${toggle.name}`)}</span>
            </span>
          </label>
        ))}

        {saved.webhook_url && (
          <div className="grid grid-cols-1 gap-4 rounded-lg bg-indigo-50/50 p-4 ring-1 ring-inset ring-indigo-100">
            <p className="text-[13px] text-zinc-600">{t(`channels.webhookHelp.${kind}`)}</p>
            <CopyField label={t("channels.webhookUrl")} value={saved.webhook_url} />
            {saved.verify_token && <CopyField label={t("channels.verifyToken")} value={saved.verify_token} />}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 pt-4">
          <label className="flex items-center gap-2 text-sm font-medium text-zinc-800">
            <input type="checkbox" className="h-4 w-4" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
            {t(`channels.enable.${kind}`)}
          </label>
          <div className="flex flex-wrap items-center gap-2">
            {testWithNumber && (
              <input
                className="input !h-9 w-44 !text-sm"
                type="tel"
                inputMode="tel"
                placeholder={t("channels.testNumber")}
                aria-label={t("channels.testNumber")}
                value={testTo}
                onChange={(e) => setTestTo(e.target.value)}
              />
            )}
            <Button variant="secondary" disabled={test.isPending || saved.status === "not_set"} onClick={() => test.mutate()}>
              {test.isPending ? t("channels.testing") : t(testTo ? "channels.sendTest" : "channels.test")}
            </Button>
            <button type="submit" className="btn btn-primary" disabled={save.isPending}>
              {save.isPending ? t("common.saving") : t("common.save")}
            </button>
          </div>
        </div>
        {saved.last_error && (
          <p className={`rounded-lg px-3 py-2 text-[13px] ${saved.status === "error" ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-700"}`}>
            {saved.last_error}
            {saved.last_checked_at && (
              <span className="ml-1 opacity-70">· {formatDateTime(saved.last_checked_at, { dateStyle: "medium", timeStyle: "short" })}</span>
            )}
          </p>
        )}
      </form>
    </section>
  );
}
