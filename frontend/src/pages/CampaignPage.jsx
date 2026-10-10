import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { useAudience, useCampaign, useCampaignRecipients, useProducts, useSegments } from "../hooks/useApi";
import { BackLink } from "../components/DocumentView";
import Sheet from "../components/Sheet";
import { AudienceCount, AudienceSheet } from "../components/marketing";
import { Button, ErrorState, Field, ListSkeleton, StatusBadge } from "../components/ui";
import { errorMessage, formatDateTime, formatMoney } from "../utils/format";
import { onSpecial } from "../utils/products";
import { celebrate } from "../utils/motion";
import { campaignDate } from "./MarketingPage";

const FIELDS = ["name", "subject", "preheader", "body", "product_ids", "cta_text", "cta_url", "segment_id"];
const MAX_PRODUCTS = 12;

// A brand-new campaign carries a placeholder name; show it as a hint
// rather than text the user has to delete before typing.
const toForm = (c, untitled) =>
  Object.fromEntries(FIELDS.map((f) => [f, f === "product_ids" ? c[f] ?? [] : f === "name" && c.name === untitled ? "" : c[f] ?? ""]));
const toPayload = (form, untitled) => ({
  ...form,
  name: form.name.trim() || untitled,
  preheader: form.preheader || null,
  cta_text: form.cta_text || null,
  cta_url: form.cta_url || null,
  segment_id: form.segment_id || null,
});

export default function CampaignPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const { data: campaign, isLoading, isError, refetch } = useCampaign(id);

  if (isLoading) return <ListSkeleton rows={4} />;
  if (isError) return <ErrorState onRetry={refetch} />;

  return (
    <>
      <BackLink to="/marketing">{t("nav.marketing")}</BackLink>
      {["draft", "scheduled"].includes(campaign.status) ? <Editor campaign={campaign} /> : <Report campaign={campaign} />}
    </>
  );
}

function Preview({ id, version }) {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["campaign", id, "preview", version],
    queryFn: () => apiClient.get(`/marketing/campaigns/${id}/preview`).then((r) => r.data),
    placeholderData: (previous) => previous,
  });
  return (
    <div className="card overflow-hidden">
      <div className="border-b border-zinc-100 px-4 py-2.5 text-xs text-zinc-500">
        <span className="font-medium text-zinc-700">{t("marketing.preview")}</span>
        {data && <span> · {data.subject}</span>}
      </div>
      {/* sandbox with no permissions: the preview can't run script or navigate the app. */}
      <iframe title={t("marketing.preview")} sandbox="" srcDoc={data?.html ?? ""} className="block h-[640px] w-full bg-zinc-50" />
    </div>
  );
}

function Editor({ campaign }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const canSend = ["admin", "manager"].includes(user?.role);

  const untitled = t("marketing.untitled");
  const [form, setForm] = useState(() => toForm(campaign, untitled));
  const [savedVersion, setSavedVersion] = useState(campaign.updated_at);
  const [dirty, setDirty] = useState(false);
  const [sheet, setSheet] = useState(null); // send | schedule | delete | audience
  const [when, setWhen] = useState("");
  const sendButton = useRef(null);

  const { data: segments = [] } = useSegments();
  const { data: products = [] } = useProducts({ is_active: true });
  const segment = segments.find((s) => s.id === form.segment_id);
  const { data: audience, isFetching: audienceLoading } = useAudience(segment?.rules ?? []);

  const save = useMutation({
    mutationFn: (payload) => apiClient.put(`/marketing/campaigns/${campaign.id}`, payload).then((r) => r.data),
    onSuccess: (saved) => {
      queryClient.setQueryData(["campaign", campaign.id], saved);
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      setSavedVersion(saved.updated_at);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  // Autosave a moment after typing stops, like any modern editor.
  const latest = useRef(form);
  latest.current = form;
  useEffect(() => {
    if (!dirty || !canWrite) return undefined;
    const timer = setTimeout(() => {
      setDirty(false);
      save.mutate(toPayload(latest.current, untitled));
    }, 700);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, dirty]);

  const set = (field) => (event) => {
    setForm((prev) => ({ ...prev, [field]: event.target.value }));
    setDirty(true);
  };
  const toggleProduct = (productId) => {
    setForm((prev) => {
      const has = prev.product_ids.includes(productId);
      if (!has && prev.product_ids.length >= MAX_PRODUCTS) return prev;
      return { ...prev, product_ids: has ? prev.product_ids.filter((p) => p !== productId) : [...prev.product_ids, productId] };
    });
    setDirty(true);
  };

  const flush = async () => {
    if (dirty) {
      setDirty(false);
      await save.mutateAsync(toPayload(latest.current, untitled));
    }
  };

  const after = (saved, message) => {
    queryClient.setQueryData(["campaign", campaign.id], saved);
    queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    setSheet(null);
    toast.success(message);
  };

  const test = useMutation({
    mutationFn: async () => {
      await flush();
      return apiClient.post(`/marketing/campaigns/${campaign.id}/test`).then((r) => r.data);
    },
    onSuccess: (r) => toast.success(t("marketing.testSent"), { description: r.sent_to }),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const send = useMutation({
    mutationFn: async (scheduledAt) => {
      await flush();
      return apiClient.post(`/marketing/campaigns/${campaign.id}/send`, { scheduled_at: scheduledAt }).then((r) => r.data);
    },
    onSuccess: (saved) => {
      // Celebrate before the sheet closes, from the button that was pressed.
      if (saved.status === "sending") celebrate(sendButton.current, { count: 18 });
      after(saved, t(saved.status === "scheduled" ? "marketing.scheduledToast" : "marketing.sendingToast"));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const unschedule = useMutation({
    mutationFn: () => apiClient.post(`/marketing/campaigns/${campaign.id}/unschedule`).then((r) => r.data),
    onSuccess: (saved) => after(saved, t("marketing.unscheduledToast")),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: () => apiClient.delete(`/marketing/campaigns/${campaign.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success(t("marketing.deleted"));
      navigate("/marketing");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const ready = form.subject.trim() && form.body.trim();
  const status = save.isPending || dirty ? t("common.saving") : t("marketing.saved");

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-2xl font-semibold tracking-tight text-zinc-900">{form.name || t("marketing.untitled")}</h1>
            <StatusBadge status={campaign.status} />
          </div>
          <p className="mt-1 text-sm text-zinc-500">
            {campaignDate(campaign, t)} · <span aria-live="polite">{status}</span>
          </p>
        </div>
        {canWrite && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setSheet("delete")}>
              {t("common.delete")}
            </Button>
            <Button variant="secondary" disabled={!ready || test.isPending} onClick={() => test.mutate()}>
              {test.isPending ? t("common.sending") : t("marketing.sendTest")}
            </Button>
            {campaign.status === "scheduled" ? (
              canSend && (
                <Button variant="secondary" disabled={unschedule.isPending} onClick={() => unschedule.mutate()}>
                  {t("marketing.unschedule")}
                </Button>
              )
            ) : (
              canSend && (
                <Button variant="secondary" disabled={!ready} onClick={() => setSheet("schedule")}>
                  {t("marketing.schedule")}
                </Button>
              )
            )}
            {canSend && (
              <Button disabled={!ready} onClick={() => setSheet("send")}>
                {t("marketing.sendNow")}
              </Button>
            )}
          </div>
        )}
      </div>
      {!canSend && canWrite && <p className="rounded-lg bg-amber-50 px-4 py-2.5 text-sm text-amber-800">{t("marketing.managerSends")}</p>}

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <fieldset disabled={!canWrite} className="space-y-5">
          <section className="card space-y-4 p-4 sm:p-5">
            <Field label={t("marketing.field.name")} hint={t("marketing.field.nameHint")}>
              <input className="input" maxLength={150} value={form.name} onChange={set("name")} placeholder={untitled} autoFocus={!form.name} />
            </Field>
            <Field label={t("marketing.field.audience")}>
              <div className="flex gap-2">
                <select className="input flex-1" value={form.segment_id} onChange={set("segment_id")}>
                  <option value="">{t("marketing.allSubscribers")}</option>
                  {segments.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
                <Button variant="secondary" onClick={() => setSheet("audience")}>
                  {t("marketing.newAudienceShort")}
                </Button>
              </div>
            </Field>
            <AudienceCount audience={audience} loading={audienceLoading} />
          </section>

          <section className="card space-y-4 p-4 sm:p-5">
            <Field label={t("marketing.field.subject")}>
              <input className="input" maxLength={200} value={form.subject} onChange={set("subject")} placeholder={t("marketing.field.subjectHint")} />
            </Field>
            <Field label={t("marketing.field.preheader")} hint={t("marketing.field.preheaderHint")}>
              <input className="input" maxLength={200} value={form.preheader} onChange={set("preheader")} />
            </Field>
            <Field label={t("marketing.field.body")} hint={t("marketing.field.bodyHint")}>
              <textarea className="input" rows={8} value={form.body} onChange={set("body")} placeholder={t("marketing.field.bodyPlaceholder")} />
            </Field>
          </section>

          <section className="card p-4 sm:p-5">
            <div className="mb-3 flex items-baseline justify-between gap-2">
              <span className="label !mb-0">{t("marketing.field.products")}</span>
              <span className="text-xs text-zinc-500">{t("marketing.field.productsCount", { count: form.product_ids.length, max: MAX_PRODUCTS })}</span>
            </div>
            {products.length === 0 ? (
              <p className="text-sm text-zinc-500">{t("marketing.noProducts")}</p>
            ) : (
              <ul className="max-h-72 space-y-1 overflow-y-auto pr-1">
                {[...products]
                  .sort((a, b) => Number(onSpecial(b)) - Number(onSpecial(a)))
                  .map((p) => {
                    const checked = form.product_ids.includes(p.id);
                    return (
                      <li key={p.id}>
                        <label className={`flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 ${checked ? "bg-indigo-50/70" : "hover:bg-zinc-50"}`}>
                          <input type="checkbox" className="h-4 w-4" checked={checked} onChange={() => toggleProduct(p.id)} />
                          <span className="min-w-0 flex-1 truncate text-sm text-zinc-900">{p.name}</span>
                          {onSpecial(p) ? (
                            <span className="shrink-0 text-sm tabular-nums">
                              <span className="mr-1 text-xs text-zinc-400 line-through">{formatMoney(p.unit_price)}</span>
                              <span className="font-medium text-rose-700">{formatMoney(p.special_price)}</span>
                            </span>
                          ) : (
                            <span className="shrink-0 text-sm tabular-nums text-zinc-600">{formatMoney(p.unit_price)}</span>
                          )}
                        </label>
                      </li>
                    );
                  })}
              </ul>
            )}
            <p className="mt-3 text-xs text-zinc-500">{t("marketing.field.productsHint")}</p>
          </section>

          <section className="card grid grid-cols-1 gap-4 p-4 sm:grid-cols-[12rem_1fr] sm:p-5">
            <Field label={t("marketing.field.ctaText")}>
              <input className="input" maxLength={60} value={form.cta_text} onChange={set("cta_text")} placeholder={t("marketing.field.ctaTextHint")} />
            </Field>
            <Field label={t("marketing.field.ctaUrl")}>
              <input className="input" type="url" inputMode="url" autoCapitalize="none" value={form.cta_url} onChange={set("cta_url")} placeholder="https://" />
            </Field>
          </section>
        </fieldset>

        <div className="lg:sticky lg:top-6">
          <Preview id={campaign.id} version={savedVersion} />
        </div>
      </div>

      <Sheet
        open={sheet === "send"}
        onClose={() => setSheet(null)}
        title={t("marketing.sendTitle")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSheet(null)}>
              {t("common.cancel")}
            </Button>
            {/* Wrapper: the confetti bursts from here when it's sent. */}
            <span ref={sendButton} className="inline-flex">
              <Button disabled={send.isPending || !audience?.count} onClick={() => send.mutate(null)}>
                {send.isPending ? t("common.sending") : t("marketing.sendTo", { count: audience?.count ?? 0 })}
              </Button>
            </span>
          </>
        }
      >
        <p className="text-sm text-zinc-600">{t("marketing.sendBody", { subject: form.subject, audience: segment?.name ?? t("marketing.allSubscribers") })}</p>
        <div className="mt-3">
          <AudienceCount audience={audience} loading={audienceLoading} />
        </div>
        <p className="mt-4 text-xs text-zinc-500">{t("marketing.consentNote")}</p>
      </Sheet>

      <Sheet
        open={sheet === "schedule"}
        onClose={() => setSheet(null)}
        title={t("marketing.scheduleTitle")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSheet(null)}>
              {t("common.cancel")}
            </Button>
            <Button disabled={!when || new Date(when) <= new Date() || send.isPending} onClick={() => send.mutate(new Date(when).toISOString())}>
              {t("marketing.schedule")}
            </Button>
          </>
        }
      >
        <Field label={t("marketing.scheduleWhen")} hint={t("marketing.scheduleHint")}>
          <input className="input" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
        </Field>
      </Sheet>

      <Sheet
        open={sheet === "delete"}
        onClose={() => setSheet(null)}
        title={t("marketing.deleteTitle")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSheet(null)}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
              {t("common.delete")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-zinc-600">{t("marketing.deleteBody")}</p>
      </Sheet>

      <AudienceSheet
        open={sheet === "audience"}
        onClose={() => setSheet(null)}
        segment={null}
        onSaved={(s) => {
          setForm((prev) => ({ ...prev, segment_id: s.id }));
          setDirty(true);
        }}
      />
    </div>
  );
}

function Stat({ label, value, detail }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-zinc-900">{value}</p>
      {detail && <p className="mt-0.5 text-xs text-zinc-500">{detail}</p>}
    </div>
  );
}

function Report({ campaign }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { stats } = campaign;
  const { data: recipients = [] } = useCampaignRecipients(campaign.id, true);
  const pct = (n) => (stats.sent ? `${Math.round((n / stats.sent) * 100)}%` : "—");

  // Keep the recipient list in step while the worker is still sending.
  useEffect(() => {
    queryClient.invalidateQueries({ queryKey: ["campaign", campaign.id, "recipients"] });
  }, [stats.sent, stats.opened, campaign.id, queryClient]);

  const duplicate = useMutation({
    mutationFn: () => apiClient.post(`/marketing/campaigns/${campaign.id}/duplicate`).then((r) => r.data),
    onSuccess: (copy) => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      navigate(`/marketing/campaigns/${copy.id}`);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-2xl font-semibold tracking-tight text-zinc-900">{campaign.name}</h1>
            <StatusBadge status={campaign.status} />
          </div>
          <p className="mt-1 text-sm text-zinc-500">
            {campaign.subject} · {campaignDate(campaign, t)}
          </p>
        </div>
        {user?.role !== "viewer" && (
          <Button variant="secondary" disabled={duplicate.isPending} onClick={() => duplicate.mutate()}>
            {t("marketing.duplicate")}
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("marketing.stat.recipients")} value={stats.recipients} />
        <Stat label={t("marketing.stat.delivered")} value={stats.sent} detail={stats.failed ? t("marketing.stat.failed", { count: stats.failed }) : null} />
        <Stat label={t("marketing.stat.opened")} value={pct(stats.opened)} detail={t("marketing.stat.openedDetail", { count: stats.opened })} />
        <Stat label={t("marketing.stat.unsubscribed")} value={stats.unsubscribed} />
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <div className="card overflow-hidden">
          <div className="border-b border-zinc-100 px-5 py-3.5 text-sm font-semibold text-zinc-900">{t("marketing.stat.recipients")}</div>
          <ul className="max-h-[640px] divide-y divide-zinc-100 overflow-y-auto">
            {recipients.map((r) => (
              <li key={r.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-zinc-900">{r.customer_name ?? r.email}</p>
                  <p className="truncate text-[13px] text-zinc-500">{r.email}</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1 text-xs text-zinc-500">
                  <StatusBadge status={r.status} />
                  {r.unsubscribed_at ? (
                    <span className="text-rose-600">{t("marketing.stat.unsubscribed")}</span>
                  ) : r.opened_at ? (
                    <span>{t("marketing.openedAt", { date: formatDateTime(r.opened_at, { dateStyle: "medium", timeStyle: "short" }) })}</span>
                  ) : null}
                  {r.error && <span className="max-w-48 truncate text-red-600" title={r.error}>{r.error}</span>}
                </div>
              </li>
            ))}
          </ul>
        </div>
        <Preview id={campaign.id} version={campaign.updated_at} />
      </div>
    </div>
  );
}
