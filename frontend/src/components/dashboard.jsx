// Building blocks of the dashboard (YGT 1.2). Every figure comes from the
// company's own records; nothing here is sample data.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Avatar } from "./ui";
import { ActivityIcon, EditActivityButton, JourneyBar, PencilIcon, STAGE_LABELS } from "./crm";
import DealFormSheet from "./DealFormSheet";
import { EditCustomerSheet } from "./CustomerFormSheet";
import { useAuth } from "../context/AuthContext";
import { formatMoney, formatMoneyWhole, formatShortDate } from "../utils/format";

const Svg = ({ d, className = "h-5 w-5", ...props }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className} {...props}>
    {d}
  </svg>
);
export const Icons = {
  cash: <><rect x="2.5" y="6" width="19" height="12" rx="2" /><circle cx="12" cy="12" r="2.5" /><path d="M6 9.5v5M18 9.5v5" /></>,
  invoice: <><path d="M6 3h9l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></>,
  deals: <><path d="m11 17 2 2a1.4 1.4 0 0 0 2-2" /><path d="m14 14 2.5 2.5a1.4 1.4 0 0 0 2-2l-3.9-3.9a2 2 0 0 0-2.8 0l-.9.9a1.4 1.4 0 0 1-2-2l2.8-2.8a5 5 0 0 1 6.1-.8l.5.3a3 3 0 0 0 2 .4L22 6" /><path d="m21 3 1 11h-2M3 3 2 14l6.5 6.5a1.4 1.4 0 0 0 2-2M3 4h8" /></>,
  customers: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18.5 20a6.5 6.5 0 0 0-3-5.5" /></>,
  plusUser: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0M19 8v6M16 11h6" /></>,
  quote: <><path d="M4 5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9l-4 3v-3H5a1 1 0 0 1-1-1V5Z" /><path d="M8 9h8M8 12h5" /></>,
  activity: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.5" /></>,
  up: <path d="m6 15 6-6 6 6" />,
  down: <path d="m6 9 6 6 6-6" />,
};

/** A white card with a heading row: the dashboard's one panel shape. */
export function Panel({ title, subtitle, action, children, className = "", bodyClass = "", tour }) {
  return (
    <section className={`card flex min-w-0 flex-col ${className}`} data-tour={tour}>
      <div className="flex items-start justify-between gap-3 px-5 pb-3 pt-4">
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold text-midnight">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className={`min-h-0 flex-1 ${bodyClass}`}>{children}</div>
    </section>
  );
}

export function ViewAll({ to, children }) {
  return (
    <Link to={to} className="inline-flex shrink-0 items-center gap-1 rounded-md text-xs font-semibold text-blue-600 hover:text-blue-800">
      {children}
      <Svg d={Icons.arrow} className="h-3.5 w-3.5" />
    </Link>
  );
}

/* ---------------------------------------------------------------- KPIs */

const TONES = {
  blue: "bg-blue-50 text-blue-600 ring-blue-100",
  emerald: "bg-emerald-50 text-emerald-600 ring-emerald-100",
  violet: "bg-violet-50 text-violet-600 ring-violet-100",
  amber: "bg-amber-50 text-amber-600 ring-amber-100",
  rose: "bg-rose-50 text-rose-600 ring-rose-100",
};

/** Small trend line for a KPI: only drawn from real history. */
function Sparkline({ values, color }) {
  const max = Math.max(...values, 0);
  if (values.length < 2 || max <= 0) return null;
  const w = 96;
  const h = 28;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - 2 - (v / max) * (h - 4)]);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-7 w-24" aria-hidden="true">
      <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts.at(-1)[0]} cy={pts.at(-1)[1]} r="2.5" fill={color} />
    </svg>
  );
}

/** One headline number. `change` is a real month-on-month comparison or
 *  null. With `to` the card is a link; without, a plain figure. */
export function KpiCard({ to, icon, tone, label, value, detail, change, spark, sparkColor, compact = false }) {
  const { t } = useTranslation();
  const Shell = to ? Link : "div";
  return (
    <Shell
      {...(to && { to })}
      className={`card group flex min-w-0 flex-col p-3.5 ${compact ? "sm:p-4" : "sm:p-5"} ${to ? "transition-shadow duration-150 hover:shadow-pop" : ""}`}
    >
      <span className="flex items-center gap-2.5 sm:gap-3">
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ring-4 sm:h-10 sm:w-10 ${TONES[tone]}`}>
          <Svg d={Icons[icon]} className="h-[18px] w-[18px]" />
        </span>
        <span className="line-clamp-2 text-[13px] font-medium leading-tight text-slate-500">{label}</span>
      </span>
      <span className={`block truncate text-lg font-bold tracking-tight tabular-nums text-midnight ${compact ? "mt-2 sm:text-xl" : "mt-3 sm:text-2xl"}`}>{value}</span>
      <span className="mt-1 flex items-end justify-between gap-2">
        <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-500">
          {change != null && (
            <span className={`inline-flex items-center gap-0.5 font-semibold ${change >= 0 ? "text-emerald-600" : "text-red-600"}`}>
              <Svg d={change >= 0 ? Icons.up : Icons.down} className="h-3.5 w-3.5" />
              {t("dashboard.kpi.change", { pct: Math.abs(Math.round(change * 100)) })}
              <span className="sr-only">{t(change >= 0 ? "dashboard.kpi.up" : "dashboard.kpi.down")}</span>
            </span>
          )}
          <span className="min-w-0">{detail}</span>
        </span>
        {spark && (
          <span className="hidden shrink-0 sm:block">
            <Sparkline values={spark} color={sparkColor} />
          </span>
        )}
      </span>
    </Shell>
  );
}

/* ------------------------------------------------------- annual goal */

const DAY_MS = 86400000;

/** The year's revenue goal: deals won so far, against where you'd be if
 *  wins came evenly through the year, and what each month left needs. */
export function GoalCard({ goal, today, canEdit }) {
  const { t, i18n } = useTranslation();
  const month = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(i18n.language, { month: "short", year: "numeric" });
  const range = `${month(goal.year_start)} – ${month(goal.year_end)}`;
  if (!goal.target || Number(goal.target) <= 0) {
    return (
      <section className="card flex flex-wrap items-center justify-between gap-3 px-5 py-4">
        <div className="flex items-center gap-3">
          <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ring-4 ${TONES.blue}`}>
            <Svg d={Icons.target} className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-semibold text-midnight">{t("goal.emptyTitle")}</p>
            <p className="text-xs text-slate-500">{t("goal.emptyBody")}</p>
          </div>
        </div>
        {canEdit && (
          <Link to="/settings" className="btn btn-secondary !h-9 !text-sm">
            {t("goal.set")}
          </Link>
        )}
      </section>
    );
  }
  const target = Number(goal.target);
  const won = Number(goal.won_value);
  const start = new Date(`${goal.year_start}T00:00:00`);
  const end = new Date(`${goal.year_end}T00:00:00`);
  const now = new Date(`${today}T00:00:00`);
  const elapsed = Math.min(1, Math.max(0, (now - start + DAY_MS) / (end - start + DAY_MS)));
  const pct = Math.min(100, (won / target) * 100);
  const expected = target * elapsed;
  const onPace = won >= expected * 0.95;
  const reached = won >= target;
  const monthsLeft = Math.max(1, (end.getFullYear() - now.getFullYear()) * 12 + end.getMonth() - now.getMonth() + 1);
  const perMonth = Math.max(0, target - won) / monthsLeft;
  return (
    <section className="card p-5" aria-label={t("goal.title")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ring-4 ${TONES[reached ? "emerald" : "blue"]}`}>
            <Svg d={Icons.target} className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-[15px] font-semibold text-midnight">{t("goal.title")}</h2>
            <p className="text-xs text-slate-500">{range}</p>
          </div>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${
            reached || onPace ? "bg-emerald-50 text-emerald-700 ring-emerald-200/70" : "bg-amber-50 text-amber-800 ring-amber-200/70"
          }`}
        >
          {reached ? t("goal.reached") : onPace ? t("goal.onPace") : t("goal.behind", { amount: formatMoneyWhole(expected - won) })}
        </span>
      </div>
      <p className="mt-3 text-sm text-slate-600">
        <span className="text-2xl font-bold tabular-nums text-midnight">{formatMoneyWhole(won)}</span> {t("goal.of", { target: formatMoneyWhole(target) })}
      </p>
      {/* The bar is progress; the tick is where an even pace would be today. */}
      <div className="relative mt-3">
        <div
          className="h-3 overflow-hidden rounded-full bg-slate-100"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(pct)}
          aria-label={t("goal.aria", { pct: Math.round(pct) })}
        >
          <div className={`h-full rounded-full ${reached ? "bg-emerald-500" : "bg-gradient-to-r from-blue-600 to-violet-500"}`} style={{ width: `${Math.max(pct, won > 0 ? 1.5 : 0)}%` }} />
        </div>
        {!reached && (
          <span className="absolute -top-1 h-5 w-0.5 rounded-full bg-midnight/60" style={{ left: `${elapsed * 100}%` }} title={t("goal.paceMarker")} aria-hidden="true" />
        )}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-xs text-slate-500">{t("goal.progress")}</dt>
          <dd className="font-semibold tabular-nums text-midnight">{t("goal.percent", { pct: pct < 10 ? pct.toFixed(1) : Math.round(pct) })}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">{t("goal.wonDeals")}</dt>
          <dd className="font-semibold tabular-nums text-midnight">{goal.won_count}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">{t("goal.perMonth", { count: monthsLeft })}</dt>
          <dd className="font-semibold tabular-nums text-midnight">{reached ? "—" : formatMoneyWhole(perMonth)}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">{t("goal.collected")}</dt>
          <dd className="font-semibold tabular-nums text-midnight">{formatMoneyWhole(goal.collected)}</dd>
        </div>
      </dl>
    </section>
  );
}

/** A row of headline figures above a list. */
export function StatStrip({ children }) {
  return <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">{children}</div>;
}

/* ------------------------------------------------------------ pipeline */

const STAGE_TONE = {
  lead: { col: "bg-blue-50/70", head: "text-blue-700", dot: "bg-blue-500" },
  qualified: { col: "bg-sky-50/80", head: "text-sky-700", dot: "bg-sky-500" },
  proposal: { col: "bg-violet-50/80", head: "text-violet-700", dot: "bg-violet-500" },
  negotiation: { col: "bg-rose-50/70", head: "text-rose-700", dot: "bg-rose-500" },
  won: { col: "bg-emerald-50/80", head: "text-emerald-700", dot: "bg-emerald-500" },
};
const CARDS_PER_STAGE = 2;

/** A small pencil in a card's corner: edit without leaving the page. */
function PencilButton({ label, onClick, className = "" }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={`pressable flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/90 text-slate-400 ring-1 ring-slate-200 hover:text-blue-700 hover:ring-blue-200 ${className}`}
    >
      <PencilIcon className="h-3.5 w-3.5" />
    </button>
  );
}

function useCanWrite() {
  const { user } = useAuth();
  return user?.role !== "viewer";
}

function DealCard({ deal, customer, owner }) {
  const { t } = useTranslation();
  const canWrite = useCanWrite();
  const [editing, setEditing] = useState(false);
  const next = deal.next_activity;
  const when = deal.stage === "won" ? deal.closed_at?.slice(0, 10) : next?.due_date ?? deal.expected_close_date;
  return (
    <div className="group relative">
    {/* With a mouse the pencil appears on hover or keyboard focus, so the
        narrow cards keep their width; on touch it is always there. */}
    {canWrite && (
      <PencilButton
        label={t("edit.deal", { title: deal.title })}
        onClick={() => setEditing(true)}
        className="absolute right-2 top-2 z-[1] transition-opacity duration-150 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:focus-visible:opacity-100 [@media(hover:hover)]:group-hover:opacity-100"
      />
    )}
    <DealFormSheet open={editing} onClose={() => setEditing(false)} deal={deal} />
    <Link to={`/deals/${deal.id}`} className="block rounded-xl border border-white bg-white p-3 shadow-card [@media(hover:none)]:pr-10 transition-shadow duration-150 hover:shadow-pop">
      <span className="line-clamp-2 text-[13px] font-semibold leading-snug text-midnight">{deal.title}</span>
      <JourneyBar milestones={deal.milestones} className="my-1.5" />
      <span className="mt-0.5 block truncate text-xs text-slate-500">{customer?.name ?? "…"}</span>
      <span className="mt-2 flex items-center justify-between gap-2">
        <span className="text-[13px] font-semibold tabular-nums text-slate-900">{formatMoneyWhole(deal.value)}</span>
        {owner && (
          <span title={owner.full_name}>
            <Avatar name={owner.full_name} size="sm" />
          </span>
        )}
      </span>
      {when && (
        <span className="mt-1 block truncate text-[11px] text-slate-400">
          {deal.stage === "won" ? t("dashboard.pipeline.wonOn", { date: formatShortDate(when) }) : next ? `${next.subject} · ${formatShortDate(when)}` : t("dashboard.pipeline.closes", { date: formatShortDate(when) })}
        </span>
      )}
    </Link>
    </div>
  );
}

/** The pipeline at a glance: each open stage, then this month's wins.
 *  Columns scroll sideways on a phone (snap to a column). */
export function PipelineBoard({ stages, deals, customers, team }) {
  const { t } = useTranslation();
  return (
    <div className="-mx-1 flex snap-x snap-mandatory gap-3 overflow-x-auto px-1 pb-1 [scrollbar-width:thin] lg:grid lg:snap-none lg:grid-cols-5 lg:overflow-visible">
      {stages.map((s) => {
        const tone = STAGE_TONE[s.stage];
        const list = deals.filter((d) => d.stage === s.stage).sort((a, b) => Number(b.value) - Number(a.value));
        const more = Math.max(0, s.count - CARDS_PER_STAGE);
        return (
          <section key={s.stage} className={`flex w-[15rem] shrink-0 snap-start flex-col rounded-2xl p-2.5 lg:w-auto ${tone.col}`} aria-label={STAGE_LABELS[s.stage]}>
            <header className="px-1 pb-2">
              <h3 className={`flex items-center gap-1.5 text-[13px] font-semibold ${tone.head}`}>
                <span className={`h-2 w-2 rounded-full ${tone.dot}`} aria-hidden="true" />
                {s.stage === "won" ? t("dashboard.pipeline.wonThisMonth") : STAGE_LABELS[s.stage]}
              </h3>
              <p className="mt-0.5 text-xs text-slate-500">
                {t("dashboard.deals", { count: s.count })} · <span className="tabular-nums">{formatMoneyWhole(s.value)}</span>
              </p>
            </header>
            <div className="flex flex-1 flex-col gap-2">
              {list.slice(0, CARDS_PER_STAGE).map((d) => (
                <DealCard key={d.id} deal={d} customer={customers.get(d.customer_id)} owner={team.get(d.owner_id)} />
              ))}
              {!list.length && <p className="rounded-xl border border-dashed border-slate-300/70 px-3 py-4 text-center text-xs text-slate-400">{t("dashboard.pipeline.empty")}</p>}
            </div>
            {more > 0 && (
              <Link to="/deals" className="mt-2 px-1 text-xs font-semibold text-slate-600 hover:text-midnight">
                {t("dashboard.pipeline.more", { count: more })}
              </Link>
            )}
          </section>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------- quick actions */

export function QuickActions({ actions }) {
  return (
    <ul className="grid grid-cols-2 gap-2 px-4 pb-4 sm:grid-cols-3 xl:grid-cols-2">
      {actions.map((a) => (
        <li key={a.to}>
          <Link to={a.to} className="pressable flex h-full items-center gap-2.5 rounded-xl border border-slate-200/80 px-2.5 py-2.5 text-[13px] font-medium leading-tight text-slate-700 transition-colors duration-150 hover:border-blue-200 hover:bg-blue-50/60 hover:text-blue-700">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
              <Svg d={Icons[a.icon]} className="h-4 w-4" />
            </span>
            <span className="min-w-0">{a.label}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/* ---------------------------------------------------- upcoming activity */

const ACT_TINT = { call: "bg-amber-50 text-amber-600", meeting: "bg-blue-50 text-blue-600", task: "bg-emerald-50 text-emerald-600", email: "bg-violet-50 text-violet-600", deadline: "bg-rose-50 text-rose-600" };

export function UpcomingList({ items, customers, today, onToggle }) {
  const { t } = useTranslation();
  return (
    <ul className="divide-y divide-slate-100">
      {items.map((a) => {
        const late = a.due_date < today;
        const day = late ? t("due.overdueTitle") : a.due_date === today ? t("due.today") : formatShortDate(a.due_date);
        const customer = customers.get(a.customer_id);
        const href = a.deal_id ? `/deals/${a.deal_id}` : a.customer_id ? `/customers/${a.customer_id}` : "/activities";
        return (
          <li key={a.id} className="flex items-center gap-3 px-5 py-3">
            <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${ACT_TINT[a.type] ?? ACT_TINT.task}`}>
              <ActivityIcon type={a.type} className="h-4 w-4" />
            </span>
            <Link to={href} className="min-w-0 flex-1">
              <span className={`block text-xs ${late ? "font-semibold text-red-600" : "text-slate-500"}`}>
                {day}
                {a.due_time && ` · ${a.due_time.slice(0, 5)}`}
              </span>
              <span className="block truncate text-sm font-medium text-midnight hover:underline">{a.subject}</span>
              {customer && <span className="block truncate text-xs text-slate-500">{customer.name}</span>}
            </Link>
            <EditActivityButton activity={a} />
            <button
              type="button"
              onClick={() => onToggle(a)}
              aria-label={t("dashboard.upcoming.markDone", { subject: a.subject })}
              className="pressable flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-200 text-slate-400 hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-600"
            >
              <Svg d={<path d="m5 12.5 4.5 4.5L19 7.5" />} className="h-4 w-4" />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/* ------------------------------------------------------- revenue chart */

const SERIES = [
  { key: "invoiced", color: "#2563EB" },
  { key: "collected", color: "#059669" },
];

function niceMax(v) {
  if (v <= 0) return 1000;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v);
}

/** Invoiced vs collected per month, one shared rand axis. Crosshair and
 *  tooltip on hover or keyboard; a table for screen readers. */
export function RevenueChart({ months }) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const [hover, setHover] = useState(null);
  // Drawn at the container's own width (not scaled), so labels stay legible.
  const box = useRef(null);
  const [W, setW] = useState(560);
  useEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(([entry]) => setW(Math.max(260, Math.round(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = W < 420 ? 190 : 230;
  const pad = { l: 48, r: W < 420 ? 58 : 66, t: 12, b: 26 };
  const max = niceMax(Math.max(...months.flatMap((m) => [m.invoiced, m.collected])));
  const x = (i) => pad.l + (months.length === 1 ? 0 : (i / (months.length - 1)) * (W - pad.l - pad.r));
  const y = (v) => pad.t + (1 - v / max) * (H - pad.t - pad.b);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const label = (iso, long) => new Date(`${iso}T00:00:00`).toLocaleDateString(i18n.language, { month: long ? "long" : "short", ...(long ? { year: "numeric" } : {}) });
  const compact = (v) => (v >= 1e6 ? `R${(v / 1e6).toFixed(1)}m` : v >= 1e3 ? `R${Math.round(v / 1e3)}k` : `R${Math.round(v)}`);
  const path = (key) => months.map((m, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(m[key]).toFixed(1)}`).join(" ");
  const area = `${path("invoiced")} L${x(months.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const every = Math.max(1, Math.ceil(months.length / Math.max(2, Math.floor((W - pad.l - pad.r) / 56))));
  const h = hover != null ? months[hover] : null;

  const pick = (clientX, rect) => {
    const px = ((clientX - rect.left) / rect.width) * W;
    const i = Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (months.length - 1));
    setHover(Math.min(months.length - 1, Math.max(0, i)));
  };

  return (
    <div className="relative" ref={box}>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-xs text-slate-600">
        {SERIES.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className="h-[3px] w-4 rounded-full" style={{ background: s.color }} aria-hidden="true" />
            {t(`dashboard.revenue.${s.key}`)}
          </span>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width={W}
        height={H}
        className="block max-w-full touch-pan-y rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-blue-600/40"
        role="img"
        aria-labelledby={`${id}-sum`}
        tabIndex={0}
        onPointerMove={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
        onPointerLeave={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") setHover((v) => Math.min(months.length - 1, (v ?? -1) + 1));
          if (e.key === "ArrowLeft") setHover((v) => Math.max(0, (v ?? months.length) - 1));
          if (e.key === "Escape") setHover(null);
        }}
        onBlur={() => setHover(null)}
      >
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="#E2E8F0" strokeDasharray={v ? "3 4" : undefined} />
            <text x={pad.l - 8} y={y(v) + 4} textAnchor="end" className="fill-slate-400 text-[11px] tabular-nums">
              {compact(v)}
            </text>
          </g>
        ))}
        {months.map((m, i) =>
          i % every === (months.length - 1) % every ? (
            <text key={m.month} x={x(i)} y={H - 6} textAnchor="middle" className="fill-slate-400 text-[11px]">
              {label(m.month)}
            </text>
          ) : null
        )}
        <defs>
          <linearGradient id={`${id}-fill`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#2563EB" stopOpacity="0.14" />
            <stop offset="100%" stopColor="#2563EB" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill={`url(#${id}-fill)`} />
        {SERIES.map((s) => (
          <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {/* Direct labels at the line ends: identity never by colour alone. */}
        {SERIES.map((s) => {
          const last = months.at(-1)[s.key];
          const other = months.at(-1)[s.key === "invoiced" ? "collected" : "invoiced"];
          const nudge = Math.abs(y(last) - y(other)) < 14 ? (last >= other ? -7 : 7) : 0;
          return (
            <text key={s.key} x={x(months.length - 1) + 8} y={y(last) + 4 + nudge} className="fill-slate-600 text-[11px] font-medium">
              {t(`dashboard.revenue.${s.key}`)}
            </text>
          );
        })}
        {h && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={y(0)} stroke="#94A3B8" strokeDasharray="3 3" />
            {SERIES.map((s) => (
              <circle key={s.key} cx={x(hover)} cy={y(h[s.key])} r="4.5" fill={s.color} stroke="#fff" strokeWidth="2" />
            ))}
          </g>
        )}
      </svg>
      {h && (
        <div
          className="pointer-events-none absolute top-8 z-10 min-w-[10rem] -translate-x-1/2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs shadow-pop"
          style={{ left: `clamp(5rem, ${(x(hover) / W) * 100}%, calc(100% - 5rem))` }}
        >
          <p className="font-semibold text-midnight">{label(h.month, true)}</p>
          {SERIES.map((s) => (
            <p key={s.key} className="mt-1 flex items-center justify-between gap-4 text-slate-600">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ background: s.color }} aria-hidden="true" />
                {t(`dashboard.revenue.${s.key}`)}
              </span>
              <span className="font-semibold tabular-nums text-slate-900">{formatMoney(h[s.key])}</span>
            </p>
          ))}
        </div>
      )}
      <p id={`${id}-sum`} className="sr-only">
        {t("dashboard.revenue.summary", {
          invoiced: formatMoney(months.reduce((n, m) => n + m.invoiced, 0)),
          collected: formatMoney(months.reduce((n, m) => n + m.collected, 0)),
          count: months.length,
        })}
      </p>
      <table className="sr-only">
        <caption>{t("dashboard.revenue.title")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("dashboard.revenue.month")}</th>
            <th scope="col">{t("dashboard.revenue.invoiced")}</th>
            <th scope="col">{t("dashboard.revenue.collected")}</th>
          </tr>
        </thead>
        <tbody>
          {months.map((m) => (
            <tr key={m.month}>
              <th scope="row">{label(m.month, true)}</th>
              <td>{formatMoney(m.invoiced)}</td>
              <td>{formatMoney(m.collected)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------- who owes you */

const OWE_STATUS = {
  overdue: "bg-red-50 text-red-700 ring-red-200/70",
  soon: "bg-amber-50 text-amber-800 ring-amber-200/70",
  pending: "bg-slate-100 text-slate-600 ring-slate-200",
};

export function OwedList({ invoices, customers, today }) {
  const { t } = useTranslation();
  const soon = useMemo(() => {
    const d = new Date(`${today}T00:00:00`);
    d.setDate(d.getDate() + 7);
    return d.toISOString().slice(0, 10);
  }, [today]);
  return (
    <ul className="divide-y divide-slate-100">
      {invoices.map((inv) => {
        const due = inv.due_date;
        const state = inv.status === "overdue" || (due && due < today) ? "overdue" : due && due <= soon ? "soon" : "pending";
        const name = customers.get(inv.customer_id)?.name ?? "…";
        return (
          <li key={inv.id}>
            <Link to={`/invoices/${inv.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50">
              <Avatar name={name} size="md" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-midnight">{name}</span>
                <span className="block text-xs text-slate-500">
                  {inv.invoice_number}
                  {due && ` · ${t("dashboard.owes.due", { date: formatShortDate(due) })}`}
                </span>
              </span>
              <span className="flex shrink-0 flex-col items-end gap-1">
                <span className="text-sm font-semibold tabular-nums text-midnight">{formatMoney(Number(inv.total) - Number(inv.amount_paid))}</span>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${OWE_STATUS[state]}`}>{t(`dashboard.owes.${state}`)}</span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/* ---------------------------------------------------- recent customers */

/** A list on narrow screens; a row of five on wide ones. */
export function RecentCustomers({ rows }) {
  const { t } = useTranslation();
  const canWrite = useCanWrite();
  const [editing, setEditing] = useState(null);
  return (
    <>
    {editing && <EditCustomerSheet id={editing} onClose={() => setEditing(null)} />}
    <ul className="divide-y divide-slate-100 xl:grid xl:grid-cols-5 xl:gap-3 xl:divide-y-0 xl:px-4 xl:pb-4">
      {rows.map((c) => (
        <li key={c.id} className="relative min-w-0">
          {canWrite && <PencilButton label={t("edit.customer", { name: c.name })} onClick={() => setEditing(c.id)} className="absolute right-3 top-1/2 z-[1] -translate-y-1/2 xl:top-3 xl:translate-y-0" />}
          <Link to={`/customers/${c.id}`} className="flex items-center gap-3 py-3 pl-5 pr-14 hover:bg-slate-50 xl:h-full xl:flex-col xl:items-start xl:rounded-xl xl:border xl:border-slate-200/80 xl:p-3.5">
            <Avatar name={c.name} size="md" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-midnight">{c.name}</span>
              <span className="block truncate text-xs text-slate-500">
                {c.last_activity_at ? t("dashboard.recent.lastActive", { date: formatShortDate(c.last_activity_at.slice(0, 10)) }) : t("dashboard.recent.noActivity")}
              </span>
            </span>
            <span className="shrink-0 text-right text-xs xl:text-left">
              {Number(c.balance) > 0 ? (
                <span className="block font-semibold tabular-nums text-midnight">{t("dashboard.recent.owes", { amount: formatMoneyWhole(c.balance) })}</span>
              ) : (
                <span className="block text-slate-400">{t("dashboard.recent.settled")}</span>
              )}
              {c.open_deals > 0 && <span className="block text-slate-500">{t("dashboard.openDeals", { count: c.open_deals })}</span>}
            </span>
          </Link>
        </li>
      ))}
    </ul>
    </>
  );
}
