import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { useBilling, usePlans } from "../hooks/useApi";
import { errorMessage, formatDate, formatMoney, formatMoneyWhole } from "../utils/format";
import { celebrate } from "../utils/motion";
import { Button } from "./ui";
import { DocumentViewer } from "./Documents";

const DAY = 24 * 60 * 60 * 1000;

function daysLeft(iso) {
  return Math.max(0, Math.ceil((new Date(iso) - Date.now()) / DAY));
}

/** During a trial: everyone added stays. With more people than Hustle
 *  covers, after the trial it's Grow or Scale, billed per person. */
export function AfterTrialNote({ billing, compact = false }) {
  const { t } = useTranslation();
  const { data: plans } = usePlans();
  const hustle = plans?.find((p) => p.key === "hustle");
  const grow = plans?.find((p) => p.key === "grow");
  if (!billing || billing.state !== "trialing" || !hustle || !grow) return null;
  const people = billing.usage.users;
  const limit = hustle.max_users;
  if (people <= limit) {
    return compact ? null : <p className="text-sm text-zinc-600">{t("billing.afterTrial.small", { limit })}</p>;
  }
  const seat = people >= (grow.team_seats ?? 3) ? (grow.team_monthly_cents ?? grow.monthly_cents) : grow.monthly_cents;
  const body = t("billing.afterTrial.big", { count: people, limit, price: formatMoneyWhole(seat / 100) });
  if (compact) return <span className="mt-0.5 block text-amber-900">{body}</span>;
  return (
    <div className="rounded-xl bg-amber-50 p-3 ring-1 ring-inset ring-amber-200/80" role="status">
      <p className="text-sm font-semibold text-amber-950">{t("billing.afterTrial.title")}</p>
      <p className="mt-0.5 text-sm text-amber-900">{body}</p>
    </div>
  );
}

/** What a plan includes, as short lines for its card. */
function planLines(plan, t) {
  const lines = [];
  if (plan.per_user) lines.push(t("billing.lines.seats"));
  else lines.push(t("billing.lines.users", { count: plan.max_users }));
  if (plan.max_customers) lines.push(t("billing.lines.customers", { count: plan.max_customers }));
  if (plan.invoices_per_month) lines.push(t("billing.lines.invoices", { count: plan.invoices_per_month }));
  if (!plan.max_customers && !plan.invoices_per_month) lines.push(t("billing.lines.unlimited"));
  lines.push(t("billing.lines.core"));
  lines.push(t("billing.features.custom_fields")); // in every plan
  plan.features.forEach((f) => lines.push(t(`billing.features.${f}`)));
  return lines;
}

/** The price of one seat: the full price for 1–2 seats, the team price
 *  once a company takes `team_seats` or more. */
export function seatCents(plan, interval, users = 1) {
  const annual = interval === "annually";
  const team = plan.team_monthly_cents != null && users >= plan.team_seats;
  if (team) return annual ? plan.team_annual_cents : plan.team_monthly_cents;
  return annual ? plan.annual_cents : plan.monthly_cents;
}

/** Price per seat for the seats chosen ("R183 per seat / month"), the full
 *  price struck through once the team price applies, and the total. */
export function PlanPrice({ plan, interval, users = 1 }) {
  const { t } = useTranslation();
  const annual = interval === "annually";
  const cents = seatCents(plan, interval, users);
  const full = annual ? plan.annual_cents : plan.monthly_cents;
  const teamCents = annual ? plan.team_annual_cents : plan.team_monthly_cents;
  const unit = t(annual ? "billing.perYear" : "billing.perMonth");
  return (
    <div>
      <p className="flex items-baseline gap-2">
        <span className="text-3xl font-semibold tracking-tight text-zinc-900 tabular-nums">{formatMoneyWhole(cents / 100)}</span>
        {cents < full && <s className="text-base text-zinc-500 tabular-nums">{formatMoneyWhole(full / 100)}</s>}
      </p>
      <p className="mt-0.5 text-sm text-zinc-500">
        {plan.per_user ? `${t("billing.perPerson")} / ` : "/ "}
        {unit}
      </p>
      {teamCents != null &&
        (cents < full ? (
          <p className="mt-2 inline-flex rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200/70">
            {t("billing.teamPrice", { count: plan.team_seats, percent: plan.team_discount_percent })}
          </p>
        ) : (
          <p className="mt-2 text-xs font-medium text-emerald-700 tabular-nums">
            {t("billing.teamFrom", { price: formatMoneyWhole(teamCents / 100), count: plan.team_seats, percent: plan.team_discount_percent })}
          </p>
        ))}
      {plan.per_user && cents > 0 && users > 1 && (
        <p className="mt-1 text-xs text-zinc-500 tabular-nums">{t("billing.total", { amount: formatMoneyWhole((cents * users) / 100), count: users })}</p>
      )}
    </div>
  );
}

/** One plan's card. `action` is the button (or nothing for Free). */
export function PlanCard({ plan, interval, users, onUsers, action, highlight = false, badge, note }) {
  const { t } = useTranslation();
  return (
    <div className={`relative flex flex-col rounded-2xl bg-white p-5 ring-1 ring-inset ${highlight ? "ring-2 ring-indigo-500" : "ring-zinc-200"}`}>
      {badge && (
        <span className="brand-bg absolute -top-2.5 left-5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold text-white">{badge}</span>
      )}
      <h3 className="font-semibold text-zinc-900">{plan.name}</h3>
      <p className="mt-0.5 text-sm text-zinc-500">{t(`billing.tagline.${plan.key}`)}</p>
      <div className="mt-4">
        <PlanPrice plan={plan} interval={interval} users={users} />
      </div>
      {plan.per_user && onUsers && (
        <label className="mt-3 flex items-center justify-between gap-3 text-sm text-zinc-600">
          {t("billing.people")}
          <span className="inline-flex items-center rounded-lg ring-1 ring-inset ring-zinc-200">
            <button type="button" className="pressable h-8 w-8 text-zinc-500 [@media(pointer:coarse)]:h-11 [@media(pointer:coarse)]:w-11" onClick={() => onUsers(Math.max(plan.min_users, users - 1))} aria-label={t("billing.fewer")}>
              −
            </button>
            <span className="w-8 text-center font-medium tabular-nums text-zinc-900">{users}</span>
            <button type="button" className="pressable h-8 w-8 text-zinc-500 [@media(pointer:coarse)]:h-11 [@media(pointer:coarse)]:w-11" onClick={() => onUsers(Math.min(500, users + 1))} aria-label={t("billing.more")}>
              +
            </button>
          </span>
        </label>
      )}
      <ul className="mt-4 flex-1 space-y-1.5 text-sm text-zinc-600">
        {planLines(plan, t).map((line) => (
          <li key={line} className="flex gap-2">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={2} className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" aria-hidden="true">
              <path d="m3.5 8.5 3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {line}
          </li>
        ))}
      </ul>
      {note && <p className="mt-4 text-xs font-medium text-amber-800">{note}</p>}
      {action && <div className={note ? "mt-2" : "mt-5"}>{action}</div>}
    </div>
  );
}

export function IntervalToggle({ value, onChange }) {
  const { t } = useTranslation();
  return (
    <div className="inline-flex rounded-xl bg-zinc-100 p-1 text-sm" role="radiogroup" aria-label={t("billing.interval")}>
      {["monthly", "annually"].map((v) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(v)}
          className={`rounded-lg px-3 py-1.5 font-medium transition-colors duration-150 [@media(pointer:coarse)]:min-h-11 ${value === v ? "bg-white text-zinc-900 shadow-sm" : "text-zinc-600 hover:text-zinc-900"}`}
        >
          {t(`billing.${v}`)}
          {v === "annually" && <span className="ml-1.5 text-xs font-semibold text-emerald-700">{t("billing.twoFree")}</span>}
        </button>
      ))}
    </div>
  );
}

function Meter({ label, used, limit }) {
  const { t } = useTranslation();
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const full = limit !== null && used >= limit;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="text-zinc-600">{label}</span>
        <span className={`tabular-nums ${full ? "font-semibold text-rose-600" : "text-zinc-900"}`}>
          {limit === null ? t("billing.usedUnlimited", { used }) : t("billing.usedOf", { used, limit })}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-zinc-100">
        {limit !== null && (
          <div className={`h-full w-full origin-left rounded-full ${full ? "bg-rose-500" : "bg-indigo-500"}`} style={{ transform: `scaleX(${pct / 100})` }} />
        )}
      </div>
    </div>
  );
}

const STATE_TONE = {
  trialing: "bg-indigo-50 text-indigo-700 ring-indigo-200/70",
  active: "bg-emerald-50 text-emerald-700 ring-emerald-200/70",
  past_due: "bg-rose-50 text-rose-700 ring-rose-200/70",
  cancelled: "bg-amber-50 text-amber-700 ring-amber-200/70",
};

/** One line saying where the subscription stands. */
function stateLine(billing, t) {
  switch (billing.state) {
    case "trialing":
      return t("billing.state.trialingLine", { count: daysLeft(billing.trial_ends_at), date: formatDate(billing.trial_ends_at) });
    case "active":
      return t("billing.state.activeLine", { date: formatDate(billing.current_period_end) });
    case "past_due":
      return t("billing.state.pastDueLine");
    case "cancelled":
      return t("billing.state.cancelledLine", { date: formatDate(billing.current_period_end) });
    case "trial_ended":
      return t("billing.state.trialEndedLine");
    case "lapsed":
      return t("billing.state.lapsedLine");
    default:
      return t("billing.state.freeLine");
  }
}

/** Settings > Billing: the company's plan, usage, plans to choose from,
 *  and payments. Checkout happens on Paystack's own page. */
export default function BillingSettings() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: billing } = useBilling();
  const { data: plans } = usePlans();
  const { data: invoices } = useQuery({ queryKey: ["billing", "invoices"], queryFn: () => apiClient.get("/billing/invoices").then((r) => r.data) });
  const [viewing, setViewing] = useState(null);
  const [params, setParams] = useSearchParams();
  const [interval, setInterval] = useState("monthly");
  // From Team settings ("Add seats"): that plan with the seats asked for.
  const [users, setUsers] = useState(() => {
    const seats = Number(params.get("seats"));
    const plan = params.get("plan");
    return seats > 0 && plan ? { [plan]: seats } : {};
  });
  const choosePlan = useRef(null);
  useEffect(() => {
    if (params.get("seats") && plans) choosePlan.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [plans]); // eslint-disable-line react-hooks/exhaustive-deps
  const [confirmCancel, setConfirmCancel] = useState(false);
  const planCard = useRef(null);
  const confirmed = useRef(false);

  useEffect(() => {
    if (billing?.interval && billing.state === "active") setInterval(billing.interval);
  }, [billing?.interval, billing?.state]);

  const refresh = (next) => {
    if (next) queryClient.setQueryData(["billing"], next);
    queryClient.invalidateQueries({ queryKey: ["billing"] });
  };

  const checkout = useMutation({
    mutationFn: (body) => apiClient.post("/billing/checkout", body).then((r) => r.data),
    // Paystack's page takes the card; it sends the person back here after.
    onSuccess: (data) => window.location.assign(data.authorization_url),
    onError: (error) => toast.error(errorMessage(error, t("billing.checkoutFailed"))),
  });

  // Back from Paystack: ?tab=billing&reference=...
  const reference = params.get("reference");
  useEffect(() => {
    if (!reference || confirmed.current) return;
    confirmed.current = true;
    apiClient
      .post("/billing/confirm", { reference })
      .then(({ data }) => {
        refresh(data.billing);
        if (data.confirmed) {
          toast.success(t("billing.paid", { plan: t(`billing.planName.${data.billing.plan}`) }));
          requestAnimationFrame(() => celebrate(planCard.current));
        } else {
          toast(t("billing.notPaid"));
        }
      })
      .catch((error) => toast.error(errorMessage(error, t("billing.confirmFailed"))))
      .finally(() => setParams({ tab: "billing" }, { replace: true }));
  }, [reference]); // eslint-disable-line react-hooks/exhaustive-deps

  const cancel = useMutation({
    mutationFn: () => apiClient.post("/billing/cancel").then((r) => r.data),
    onSuccess: (next) => {
      refresh(next);
      setConfirmCancel(false);
      toast.success(t("billing.cancelled", { date: formatDate(next.current_period_end) }));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const card = useMutation({
    mutationFn: () => apiClient.post("/billing/card").then((r) => r.data),
    onSuccess: (data) => window.open(data.url, "_blank", "noopener"),
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (!billing || !plans) return <div className="card h-48 animate-pulse" />;

  const paidPlans = plans.filter((p) => p.monthly_cents > 0);
  const usersFor = (plan) => users[plan.key] ?? Math.max(plan.min_users, billing.usage.users);
  const paying = ["active", "past_due"].includes(billing.state);
  const isCurrent = (plan) =>
    paying && billing.subscribed_plan === plan.key && billing.interval === interval && (!plan.per_user || billing.seats === usersFor(plan));

  return (
    <div className="space-y-5">
      {/* ---- Where the company stands ---- */}
      <section ref={planCard} className="card p-4 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">{t("billing.yourPlan")}</p>
            <div className="mt-1 flex items-center gap-2">
              <h2 className="text-2xl font-semibold tracking-tight text-zinc-900">{t(`billing.planName.${billing.plan}`)}</h2>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${
                  STATE_TONE[billing.state] ?? "bg-zinc-100 text-zinc-600 ring-zinc-200"
                }`}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
                {t(`billing.state.${billing.state}`)}
              </span>
            </div>
            <p className="mt-1 text-sm text-zinc-600">{stateLine(billing, t)}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {billing.has_card && ["active", "past_due"].includes(billing.state) && (
              <Button variant="secondary" className="!h-9 !text-sm" onClick={() => card.mutate()} disabled={card.isPending}>
                {t("billing.updateCard")}
              </Button>
            )}
            {paying && !confirmCancel && (
              <Button variant="secondary" className="!h-9 !text-sm" onClick={() => setConfirmCancel(true)}>
                {t("billing.cancel")}
              </Button>
            )}
          </div>
        </div>

        {confirmCancel && (
          <div className="mt-4 rounded-xl bg-amber-50 p-4 ring-1 ring-inset ring-amber-200/70">
            <p className="text-sm text-amber-900">{t("billing.cancelConfirm", { date: formatDate(billing.current_period_end) })}</p>
            <div className="mt-3 flex gap-2">
              <Button variant="danger" className="!h-9 !text-sm" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
                {t("billing.cancelYes")}
              </Button>
              <Button variant="secondary" className="!h-9 !text-sm" onClick={() => setConfirmCancel(false)}>
                {t("billing.keep")}
              </Button>
            </div>
          </div>
        )}

        <div className="mt-4">
          <AfterTrialNote billing={billing} />
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <Meter label={t("billing.usage.users")} used={billing.usage.users} limit={billing.limits.users} />
          <Meter label={t("billing.usage.customers")} used={billing.usage.customers} limit={billing.limits.customers} />
          <Meter label={t("billing.usage.invoices")} used={billing.usage.invoices_this_month} limit={billing.limits.invoices_this_month} />
        </div>
      </section>

      {/* ---- Choose a plan ---- */}
      <section ref={choosePlan} className="scroll-mt-6 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-zinc-900">{t(paying ? "billing.changePlan" : "billing.choosePlan")}</h2>
            <p className="mt-0.5 text-sm text-zinc-500">{t("billing.choosePlanHint")}</p>
          </div>
          <IntervalToggle value={interval} onChange={setInterval} />
        </div>
        {!billing.payments_enabled && (
          <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-inset ring-amber-200/70">{t("billing.notConfigured")}</p>
        )}
        <div className="grid gap-4 md:grid-cols-3">
          {paidPlans.map((plan) => {
            const current = isCurrent(plan);
            const tooSmall = !plan.per_user && plan.max_users != null && billing.usage.users > plan.max_users;
            return (
              <PlanCard
                key={plan.key}
                plan={plan}
                interval={interval}
                users={usersFor(plan)}
                onUsers={(n) => setUsers((prev) => ({ ...prev, [plan.key]: n }))}
                // During a trial, the plan they chose at sign-up stands out.
                highlight={billing.state === "trialing" ? plan.key === billing.plan : plan.key === "grow"}
                badge={billing.state === "trialing" && plan.key === billing.plan ? t("billing.state.trialing") : plan.key === "grow" ? t("billing.popular") : undefined}
                note={tooSmall ? t("billing.tooSmall", { count: billing.usage.users, limit: plan.max_users }) : undefined}
                action={
                  <Button
                    className="w-full"
                    variant={plan.key === "grow" ? "primary" : "secondary"}
                    disabled={current || tooSmall || checkout.isPending || !billing.payments_enabled}
                    onClick={() => checkout.mutate({ plan: plan.key, interval, users: usersFor(plan) })}
                  >
                    {current
                      ? t("billing.current")
                      : checkout.isPending && checkout.variables?.plan === plan.key
                        ? t("billing.toPaystack")
                        : t(paying ? "billing.switchTo" : "billing.choose", { plan: plan.name })}
                  </Button>
                }
              />
            );
          })}
        </div>
        <p className="flex items-center gap-1.5 text-xs text-zinc-500">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.6} className="h-3.5 w-3.5" aria-hidden="true">
            <rect x="3" y="7" width="10" height="7" rx="1.5" />
            <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
          </svg>
          {t("billing.securedBy")}
        </p>
      </section>

      {/* ---- YGT's invoices: one per payment, ready to view and print ---- */}
      {invoices?.length > 0 && (
        <section className="card p-4 sm:p-6">
          <h2 className="text-base font-semibold text-zinc-900">{t("billing.invoices")}</h2>
          <p className="mt-0.5 text-sm text-zinc-500">{t("billing.invoicesHint")}</p>
          <ul className="mt-3 divide-y divide-zinc-100 text-sm">
            {invoices.map((inv) => (
              <li key={inv.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5">
                <span className="w-32 font-medium text-zinc-900">{inv.number}</span>
                <span className="text-zinc-600">{formatDate(inv.issued_at)}</span>
                <span className="min-w-0 flex-1 truncate text-zinc-700">
                  {t(`billing.planName.${inv.plan}`)} · {t(`billing.${inv.interval}`)}
                  {inv.seats > 1 ? ` · ${t("billing.peopleCount", { count: inv.seats })}` : ""}
                  <span className="block truncate text-xs text-zinc-400">{t("billing.paystackRef", { ref: inv.payment_reference })}</span>
                </span>
                <span className="font-medium tabular-nums text-zinc-900">{formatMoney(inv.amount_cents / 100)}</span>
                <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200/70">{t("status.paid")}</span>
                <button type="button" className="btn btn-secondary !h-8 !text-xs" onClick={() => setViewing(inv)}>
                  {t("documents.view")}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <DocumentViewer
        open={Boolean(viewing)}
        onClose={() => setViewing(null)}
        url={viewing ? `/billing/invoices/${viewing.id}/document` : null}
        title={viewing?.number ?? ""}
      />
    </div>
  );
}

// The smallest plan with each feature; anything not listed starts at Grow.
const FEATURE_PLAN = { discovery: "scale" };

/** Does the company's plan include this feature? undefined while loading. */
export function useHasFeature(feature) {
  const { data: billing } = useBilling();
  return billing ? billing.features.includes(feature) : undefined;
}

/** Shown where a feature isn't in the company's plan (WhatsApp/SMS,
 *  marketing, custom fields, team chat, reports, recurring invoices):
 *  says which plan has it. */
export function PlanNotice({ feature }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data: billing } = useBilling();
  if (!billing || billing.features.includes(feature)) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-indigo-50 p-4 ring-1 ring-inset ring-indigo-200/70">
      <div>
        <p className="text-sm font-semibold text-indigo-950">{t("billing.notice.title", { plan: t(`billing.planName.${FEATURE_PLAN[feature] ?? "grow"}`) })}</p>
        <p className="text-sm text-indigo-900/80">{t(`billing.notice.${feature}`)}</p>
      </div>
      {user?.role === "admin" ? (
        <Link to="/settings?tab=billing" className="btn btn-primary !h-9 !text-sm">
          {t("billing.seePlans")}
        </Link>
      ) : (
        <span className="text-xs text-indigo-900/70">{t("getStarted.askAdmin")}</span>
      )}
    </div>
  );
}

/** Dashboard strip for admins: trial days left, a failed payment, or
 *  being back on Free. Quiet once a plan is paid up. */
export function PlanBanner() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data: billing } = useBilling();
  if (!billing || user?.role !== "admin" || !["trialing", "past_due"].includes(billing.state)) return null;
  const urgent = billing.state !== "trialing" || daysLeft(billing.trial_ends_at) <= 3;
  const text =
    billing.state === "trialing" ? t("billing.banner.trial", { count: daysLeft(billing.trial_ends_at) }) : t("billing.banner.pastDue");
  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 rounded-xl px-4 py-3 ring-1 ring-inset ${
        urgent ? "bg-amber-50 ring-amber-200/70" : "bg-white/70 ring-zinc-200/80"
      }`}
    >
      <p className={`text-sm ${urgent ? "text-amber-900" : "text-zinc-700"}`}>
        {text}
        <AfterTrialNote billing={billing} compact />
      </p>
      <Link to="/settings?tab=billing" className={`btn ${urgent ? "btn-primary" : "btn-secondary"} !h-8 !px-3 !text-xs`}>
        {t(billing.state === "past_due" ? "billing.fixPayment" : "billing.seePlans")}
      </Link>
    </div>
  );
}


/** On every page once the trial or a paid plan has ended: everything can
 *  still be viewed; adding, editing and sending wait for a plan. */
export function LockedBanner() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data: billing } = useBilling();
  if (!billing || !["trial_ended", "lapsed"].includes(billing.state)) return null;
  return (
    <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl bg-amber-50 px-4 py-3 ring-1 ring-inset ring-amber-200/70" role="status">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-amber-950">{t(billing.state === "lapsed" ? "billing.locked.titleLapsed" : "billing.locked.title")}</p>
        <p className="text-sm text-amber-900/80">{t("billing.locked.body")}</p>
      </div>
      {user?.role === "admin" ? (
        <Link to="/settings?tab=billing" className="btn btn-primary !h-9 !text-sm">
          {t("billing.choosePlan")}
        </Link>
      ) : (
        <span className="text-sm text-amber-900/80">{t("billing.locked.askAdmin")}</span>
      )}
    </div>
  );
}
