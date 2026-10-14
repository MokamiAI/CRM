import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { PlanNotice, useHasFeature } from "../components/Billing";
import { useDiscoveryCounts } from "../hooks/useApi";
import { industryLabel, industryOptions } from "../components/crm";
import { Button, EmptyState, ErrorState, Field, FilterChips, ListSkeleton, PageHeader } from "../components/ui";
import { errorMessage, formatDate, formatMoney } from "../utils/format";

const get = (path, params) => apiClient.get(path, { params }).then((r) => r.data);
const RADII = [5, 10, 25, 50];
const MAX_INDUSTRIES = 8;
const TONE = {
  osm: "bg-sky-50 text-sky-700 ring-sky-200/70",
  quiet_customer: "bg-amber-50 text-amber-800 ring-amber-200/70",
  lost_deal: "bg-rose-50 text-rose-700 ring-rose-200/70",
  stale_quote: "bg-violet-50 text-violet-700 ring-violet-200/70",
};

/** One line on why this lead is worth a call. */
function reason(lead, t) {
  const d = lead.details ?? {};
  switch (lead.source) {
    case "stale_quote":
      return t("discovery.why.stale_quote", { number: d.number, amount: formatMoney(d.value), date: formatDate(lead.last_contact) });
    case "lost_deal":
      return t("discovery.why.lost_deal", { title: d.title, amount: formatMoney(d.value), date: formatDate(lead.last_contact) });
    case "quiet_customer":
      return t("discovery.why.quiet_customer", { amount: formatMoney(d.value), date: formatDate(lead.last_contact) });
    default:
      return [industryLabel(lead.industry), lead.kind?.replaceAll("_", " ")].filter(Boolean).join(" · ");
  }
}

/** The deal's title, in the user's language. */
function dealTitle(lead, t) {
  const d = lead.details ?? {};
  if (lead.source === "stale_quote") return t("discovery.dealTitle.stale_quote", { number: d.number, name: lead.name });
  if (lead.source === "lost_deal") return t("discovery.dealTitle.lost_deal", { title: d.title });
  if (lead.source === "quiet_customer") return t("discovery.dealTitle.quiet_customer", { name: lead.name });
  return lead.name;
}

function LeadCard({ lead, canWrite, onAdd, onDismiss, busy }) {
  const { t } = useTranslation();
  const website = lead.website?.replace(/^https?:\/\//, "").replace(/\/$/, "");
  return (
    <li className="card flex flex-col gap-3 p-4 sm:flex-row sm:items-start">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="min-w-0 truncate font-semibold text-zinc-900">
            {lead.customer_id && lead.status !== "added" ? (
              <Link to={`/customers/${lead.customer_id}`} className="hover:underline">
                {lead.name}
              </Link>
            ) : (
              lead.name
            )}
          </h3>
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${TONE[lead.source]}`}>{t(`discovery.source.${lead.source}`)}</span>
        </div>
        <p className="mt-1 text-sm text-zinc-600">{reason(lead, t)}</p>
        {(lead.address || lead.phone || website || lead.email) && (
          <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-zinc-500">
            {lead.address && <span className="min-w-0 break-words">{lead.address}</span>}
            {lead.phone && (
              <a href={`tel:${lead.phone.replace(/\s/g, "")}`} className="text-indigo-700 hover:underline">
                {lead.phone}
              </a>
            )}
            {lead.email && (
              <a href={`mailto:${lead.email}`} className="text-indigo-700 hover:underline">
                {lead.email}
              </a>
            )}
            {website && (
              <a href={lead.website} target="_blank" rel="noopener noreferrer nofollow" className="text-indigo-700 hover:underline">
                {website}
              </a>
            )}
          </p>
        )}
      </div>
      {lead.status === "new" && canWrite && (
        <div className="flex shrink-0 gap-2">
          <Button variant="secondary" className="!h-9 !text-sm" disabled={busy} onClick={() => onDismiss(lead)}>
            {t("discovery.dismiss")}
          </Button>
          <Button className="!h-9 !text-sm" disabled={busy} onClick={() => onAdd(lead)}>
            {t("discovery.add")}
          </Button>
        </div>
      )}
      {lead.status === "added" && lead.deal_id && (
        <Link to={`/deals/${lead.deal_id}`} className="btn btn-secondary !h-9 shrink-0 !text-sm">
          {t("discovery.openDeal")}
        </Link>
      )}
    </li>
  );
}

function SettingsCard({ conf, canManage }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(null);
  useEffect(() => {
    if (conf) setForm({ enabled: conf.enabled, area: conf.area ?? "", radius_km: conf.radius_km, industries: conf.industries });
  }, [conf]);
  const save = useMutation({
    mutationFn: (body) => apiClient.put("/discovery/settings", body).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.setQueryData(["discovery", "settings"], data);
      toast.success(t("discovery.settings.saved"));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  if (!form) return <div className="card h-40 animate-pulse motion-reduce:animate-none" />;

  if (!canManage) {
    return (
      <section className="card p-5 text-sm text-zinc-600">
        <h2 className="font-semibold text-zinc-900">{t("discovery.settings.title")}</h2>
        <p className="mt-1">
          {conf.area ? t("discovery.settings.summary", { area: conf.area, km: conf.radius_km }) : t("discovery.settings.noArea")}
        </p>
        {conf.industries.length > 0 && <p className="mt-1">{conf.industries.map(industryLabel).join(", ")}</p>}
      </section>
    );
  }

  const toggle = (code) =>
    setForm((f) => ({
      ...f,
      industries: f.industries.includes(code) ? f.industries.filter((c) => c !== code) : f.industries.length < MAX_INDUSTRIES ? [...f.industries, code] : f.industries,
    }));
  return (
    <form
      className="card space-y-4 p-5"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate({ ...form, area: form.area.trim() || null });
      }}
    >
      <div>
        <h2 className="font-semibold text-zinc-900">{t("discovery.settings.title")}</h2>
        <p className="mt-0.5 text-sm text-zinc-500">{t("discovery.settings.hint")}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Field label={t("discovery.settings.area")} hint={conf.area && !conf.located ? t("discovery.settings.notFound") : t("discovery.settings.areaHint")}>
          <input className="input" value={form.area} maxLength={200} placeholder={t("discovery.settings.areaPlaceholder")} onChange={(e) => setForm({ ...form, area: e.target.value })} />
        </Field>
        <Field label={t("discovery.settings.radius")}>
          <select className="input" value={form.radius_km} onChange={(e) => setForm({ ...form, radius_km: Number(e.target.value) })}>
            {RADII.map((km) => (
              <option key={km} value={km}>
                {t("discovery.settings.km", { count: km })}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <fieldset>
        <legend className="text-sm font-medium text-zinc-700">{t("discovery.settings.industries")}</legend>
        <p className="text-xs text-zinc-500">{t("discovery.settings.industriesHint", { count: MAX_INDUSTRIES })}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {industryOptions()
            .filter((o) => o.value !== "other")
            .map((o) => {
              const on = form.industries.includes(o.value);
              return (
                <button
                  key={o.value}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggle(o.value)}
                  className={`pressable rounded-full px-3 py-1 text-[13px] font-medium ring-1 ring-inset transition-colors duration-150 ${
                    on ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-zinc-600 ring-zinc-200 hover:text-zinc-900"
                  }`}
                >
                  {o.label}
                </button>
              );
            })}
        </div>
      </fieldset>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 pt-4">
        <label className="flex items-center gap-2 text-sm text-zinc-700">
          <input type="checkbox" className="h-4 w-4 rounded border-zinc-300" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
          {t("discovery.settings.weekly")}
        </label>
        <Button type="submit" disabled={save.isPending}>
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}

/** Discovery (Scale): potential customers found for the company, waiting
 *  for someone to add them to the pipeline or dismiss them. */
export default function DiscoveryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const included = useHasFeature("discovery");
  const [status, setStatus] = useState("new");
  const [showSettings, setShowSettings] = useState(false);
  const canWrite = user?.role !== "viewer";
  const canManage = ["admin", "manager"].includes(user?.role);
  const on = included === true;

  // While the map lookup runs, check every few seconds; then stop.
  const conf = useQuery({
    queryKey: ["discovery", "settings"],
    queryFn: () => get("/discovery/settings"),
    enabled: on,
    refetchInterval: (q) => (q.state.data?.nearby_status === "looking" ? 4000 : false),
  });
  const counts = useDiscoveryCounts(on);
  const leads = useQuery({ queryKey: ["discovery", "leads", status], queryFn: () => get("/discovery/leads", { status }), enabled: on });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["discovery"] });
  const nearby = conf.data?.nearby_status;
  const was = useRef(nearby);
  useEffect(() => {
    if (was.current === "looking" && nearby !== "looking") {
      queryClient.invalidateQueries({ queryKey: ["discovery", "leads"] });
      queryClient.invalidateQueries({ queryKey: ["discovery", "counts"] });
    }
    was.current = nearby;
  }, [nearby, queryClient]);
  const onError = (error) => toast.error(errorMessage(error));

  const run = useMutation({
    mutationFn: () => apiClient.post("/discovery/run").then((r) => r.data),
    onSuccess: ({ found }) => {
      refresh();
      setStatus("new");
      toast.success(t("discovery.found", { count: found }));
    },
    onError,
  });
  const add = useMutation({
    mutationFn: (lead) => apiClient.post(`/discovery/leads/${lead.id}/add`, { title: dealTitle(lead, t) }).then((r) => r.data),
    onSuccess: (lead) => {
      refresh();
      queryClient.invalidateQueries({ queryKey: ["deals"] });
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      toast.success(t("discovery.added", { name: lead.name }), { action: { label: t("discovery.openDeal"), onClick: () => navigate(`/deals/${lead.deal_id}`) } });
    },
    onError,
  });
  const dismiss = useMutation({ mutationFn: (lead) => apiClient.post(`/discovery/leads/${lead.id}/dismiss`), onSuccess: refresh, onError });

  const needsSetup = conf.data && !conf.data.located;
  const settingsOpen = showSettings || (needsSetup && canManage);
  const c = counts.data ?? {};

  return (
    <>
      <PageHeader
        title={t("discovery.title")}
        subtitle={t("discovery.subtitle")}
        actions={
          on && (
            <>
              <Button variant="secondary" onClick={() => setShowSettings((v) => !v)} aria-expanded={settingsOpen}>
                {t("discovery.settings.button")}
              </Button>
              {canManage && (
                <Button onClick={() => run.mutate()} disabled={run.isPending}>
                  {run.isPending ? t("discovery.looking") : t("discovery.lookNow")}
                </Button>
              )}
            </>
          )
        }
      />
      {included === false ? (
        <PlanNotice feature="discovery" />
      ) : included === undefined ? (
        <ListSkeleton />
      ) : (
        <div className="space-y-5">
          {settingsOpen && <SettingsCard conf={conf.data} canManage={canManage} />}
          {nearby === "looking" && (
            <p role="status" className="flex items-center gap-2.5 rounded-xl bg-sky-50 px-4 py-3 text-sm text-sky-900 ring-1 ring-inset ring-sky-200/70">
              <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-sky-500 motion-reduce:animate-none" aria-hidden="true" />
              {t("discovery.nearby.looking", { area: conf.data.area })}
            </p>
          )}
          {nearby === "failed" && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-inset ring-amber-200/70">
              <span>{t("discovery.nearby.failed")}</span>
              {canManage && (
                <button type="button" className="font-medium underline" disabled={run.isPending} onClick={() => run.mutate()}>
                  {t("discovery.nearby.retry")}
                </button>
              )}
            </div>
          )}
          <FilterChips
            value={status}
            onChange={setStatus}
            options={["new", "added", "dismissed"].map((s) => ({ value: s, label: `${t(`discovery.tab.${s}`)}${c[s] ? ` · ${c[s]}` : ""}` }))}
          />
          {leads.isLoading ? (
            <ListSkeleton />
          ) : leads.isError ? (
            <ErrorState onRetry={leads.refetch} />
          ) : leads.data.length === 0 ? (
            <EmptyState
              title={t(status === "new" ? "discovery.empty" : `discovery.emptyTab.${status}`)}
              description={status === "new" ? t(needsSetup ? "discovery.emptySetup" : "discovery.emptyHint") : undefined}
            />
          ) : (
            <ul className="space-y-3">
              {leads.data.map((lead) => (
                <LeadCard
                  key={lead.id}
                  lead={lead}
                  canWrite={canWrite}
                  busy={(add.isPending && add.variables?.id === lead.id) || (dismiss.isPending && dismiss.variables?.id === lead.id)}
                  onAdd={(l) => add.mutate(l)}
                  onDismiss={(l) => dismiss.mutate(l)}
                />
              ))}
            </ul>
          )}
          <p className="text-xs text-zinc-500">
            {t("discovery.privacy")}{" "}
            <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer" className="underline">
              © OpenStreetMap contributors
            </a>
          </p>
        </div>
      )}
    </>
  );
}
