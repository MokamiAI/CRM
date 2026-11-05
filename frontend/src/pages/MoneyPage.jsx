// The Money dashboard (Grow and Scale): twelve months of money in, money out
// and profit, where the money went, and what's still to come in and to pay
// (backend CostService.overview). Money counts when it moves. For admins
// and managers, like Costs.
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { PlanNotice, useHasFeature } from "../components/Billing";
import { EmptyState, ErrorState, FilterChips, ListSkeleton, PageHeader } from "../components/ui";
import { formatMoney, formatMoneyFit } from "../utils/format";
import { barPath, niceMax } from "../components/dashboard";
import { categoryLabel } from "./CostsPage";
import { canViewCosts } from "../utils/costAccess";

const IN = "#059669";
const OUT = "#E11D48";
const PROFIT = "#1E3A8A";
// Where the money goes: one steady colour per category, in spending order.
const CATEGORY_COLORS = ["#2563EB", "#F59E0B", "#7C3AED", "#0891B2", "#DB2777", "#65A30D", "#EA580C", "#475569"];

/** Money in and out as paired bars per month, profit as a line across them.
 *  A loss dips below the zero line. Tooltip on hover or arrow keys. */
function MoneyChart({ months }) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const [hover, setHover] = useState(null);
  const box = useRef(null);
  const [W, setW] = useState(640);
  useEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(([entry]) => setW(Math.max(260, Math.round(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = W < 420 ? 220 : 270;
  const pad = { l: 52, r: 8, t: 12, b: 26 };
  const top = niceMax(Math.max(...months.flatMap((m) => [m.in, m.out, m.profit])));
  const lowest = Math.min(0, ...months.map((m) => m.profit));
  const bottom = lowest < 0 ? -niceMax(-lowest) : 0;
  const band = (W - pad.l - pad.r) / months.length;
  const x = (i) => pad.l + band * (i + 0.5);
  const barW = Math.max(4, Math.min(20, (band * 0.62) / 2));
  const gap = Math.min(3, barW / 4);
  const y = (v) => pad.t + ((top - v) / (top - bottom)) * (H - pad.t - pad.b);
  // A small loss gets its own line only when it's far enough below zero to read.
  const ticks = [...new Set([0, top / 2, top, ...(bottom < 0 && y(bottom) - y(0) >= 16 ? [bottom] : [])])];
  const label = (iso, long) => new Date(`${iso}T00:00:00`).toLocaleDateString(i18n.language, { month: long ? "long" : "short", ...(long ? { year: "numeric" } : {}) });
  const compact = (v) => `${v < 0 ? "-" : ""}${Math.abs(v) >= 1e6 ? `R${(Math.abs(v) / 1e6).toFixed(1)}m` : Math.abs(v) >= 1e3 ? `R${Math.round(Math.abs(v) / 1e3)}k` : `R${Math.round(Math.abs(v))}`}`;
  const every = Math.max(1, Math.ceil(months.length / Math.max(2, Math.floor((W - pad.l - pad.r) / 40))));
  const h = hover != null ? months[hover] : null;
  const line = months.map((m, i) => `${i ? "L" : "M"}${x(i)},${y(m.profit)}`).join(" ");
  const series = [
    { key: "in", color: IN, label: t("money.in") },
    { key: "out", color: OUT, label: t("money.out") },
  ];

  return (
    <div className="relative" ref={box}>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-xs text-slate-600">
        {series.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: s.color }} aria-hidden="true" />
            {s.label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded" style={{ background: PROFIT }} aria-hidden="true" />
          {t("money.profit")}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width={W}
        height={H}
        className="block max-w-full touch-pan-y rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-blue-600/40"
        role="img"
        aria-labelledby={`${id}-sum`}
        tabIndex={0}
        onPointerDown={(e) => e.preventDefault()}
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const i = Math.floor((((e.clientX - rect.left) / rect.width) * W - pad.l) / band);
          setHover(Math.min(months.length - 1, Math.max(0, i)));
        }}
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
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke={v === 0 ? "#CBD5E1" : "#E2E8F0"} strokeDasharray={v === 0 ? undefined : "3 4"} />
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
        {h && <rect x={pad.l + band * hover + 2} y={pad.t} width={band - 4} height={H - pad.t - pad.b} rx="6" fill="#F1F5F9" />}
        {months.map((m, i) =>
          series.map((s, j) =>
            m[s.key] > 0 ? (
              <path key={`${m.month}-${s.key}`} d={barPath(j ? x(i) + gap / 2 : x(i) - gap / 2 - barW, barW, y(m[s.key]), y(0))} fill={s.color} opacity={0.9} />
            ) : null
          )
        )}
        <path d={line} fill="none" stroke={PROFIT} strokeWidth="2" strokeLinejoin="round" />
        {months.map((m, i) => (
          <circle key={m.month} cx={x(i)} cy={y(m.profit)} r={hover === i ? 4.5 : 3} fill={m.profit < 0 ? OUT : PROFIT} stroke="white" strokeWidth="1.5" />
        ))}
      </svg>
      {h && (
        <div
          className="pointer-events-none absolute top-8 z-10 min-w-[11rem] -translate-x-1/2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs shadow-pop"
          style={{ left: `clamp(5.5rem, ${(x(hover) / W) * 100}%, calc(100% - 5.5rem))` }}
        >
          <p className="font-semibold text-midnight">{label(h.month, true)}</p>
          {[...series, { key: "profit", color: PROFIT, label: t("money.profit") }].map((s) => (
            <p key={s.key} className="mt-1 flex items-center justify-between gap-4 text-slate-600">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ background: s.color }} aria-hidden="true" />
                {s.label}
              </span>
              <span className={`font-semibold tabular-nums ${s.key === "profit" && h.profit < 0 ? "text-red-600" : "text-slate-900"}`}>{formatMoney(h[s.key])}</span>
            </p>
          ))}
        </div>
      )}
      <p id={`${id}-sum`} className="sr-only">
        {t("money.chartSummary", {
          in: formatMoney(months.reduce((n, m) => n + m.in, 0)),
          out: formatMoney(months.reduce((n, m) => n + m.out, 0)),
          profit: formatMoney(months.reduce((n, m) => n + m.profit, 0)),
        })}
      </p>
    </div>
  );
}

function Kpi({ label, value, hint, tone }) {
  const tones = { red: "text-red-600", emerald: "text-emerald-700", amber: "text-amber-700" };
  return (
    <div className="card p-4">
      <p className="text-xs font-medium text-zinc-500">{label}</p>
      <p className={`mt-1 text-xl font-semibold tabular-nums ${tones[tone] ?? "text-zinc-900"}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-zinc-500">{hint}</p>}
    </div>
  );
}

/** Where the money went: one bar per category, as a share of all spending. */
function Categories({ rows }) {
  const { t, i18n } = useTranslation();
  const total = rows.reduce((n, r) => n + Number(r.total), 0);
  if (!rows.length) return <p className="py-6 text-center text-sm text-zinc-500">{t("money.noSpending")}</p>;
  return (
    <ul className="space-y-3">
      {rows.map((r, i) => {
        const share = total ? Number(r.total) / total : 0;
        return (
          <li key={r.category}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 truncate font-medium text-zinc-800">{categoryLabel(r.category, t)}</span>
              <span className="shrink-0 tabular-nums text-zinc-500">
                <span className="font-semibold text-zinc-900">{formatMoney(r.total)}</span> · {Math.round(share * 100).toLocaleString(i18n.language)}%
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-zinc-100">
              <div className="h-full rounded-full" style={{ width: `${Math.max(2, share * 100)}%`, background: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export default function MoneyPage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const allowed = canViewCosts(user);
  const included = useHasFeature("reports");
  const [period, setPeriod] = useState("year");
  const { data: o, isLoading, isError, refetch } = useQuery({
    queryKey: ["costs", "overview"],
    queryFn: () => apiClient.get("/costs/overview").then((r) => r.data),
    enabled: allowed && included === true,
  });

  if (!allowed) return <EmptyState title={t("money.title")} description={t("costs.notAllowed")} />;
  const header = <PageHeader title={t("money.title")} subtitle={t("money.subtitle")} />;
  if (included === false)
    return (
      <>
        {header}
        <PlanNotice feature="reports" />
        <p className="mt-4 text-sm text-zinc-600">
          {t("money.onCosts")}{" "}
          <Link to="/costs" className="font-medium text-blue-600 hover:underline">
            {t("money.openCosts")}
          </Link>
        </p>
      </>
    );
  if (isLoading || included == null)
    return (
      <>
        {header}
        <ListSkeleton />
      </>
    );
  if (isError) return <ErrorState onRetry={refetch} />;

  const months = o.months.map((m) => ({ month: m.month, in: Number(m.money_in), out: Number(m.money_out), profit: Number(m.profit) }));
  const empty = months.every((m) => !m.in && !m.out);
  const thisMonth = months.at(-1);

  return (
    <>
      {header}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label={t("money.inYear")} value={formatMoneyFit(o.money_in, 10_000_000)} hint={t("money.thisMonthValue", { value: formatMoney(thisMonth.in) })} />
        <Kpi label={t("money.outYear")} value={formatMoneyFit(o.money_out, 10_000_000)} hint={t("money.thisMonthValue", { value: formatMoney(thisMonth.out) })} />
        <Kpi
          label={t("money.profitYear")}
          value={formatMoneyFit(o.profit, 10_000_000)}
          tone={Number(o.profit) < 0 ? "red" : "emerald"}
          hint={o.margin != null ? t("costs.margin", { value: Number(o.margin).toLocaleString(i18n.language) }) : t("costs.noMargin")}
        />
        <Kpi
          label={t("money.inLimbo")}
          value={formatMoney(Number(o.to_come_in) - Number(o.to_pay))}
          tone={Number(o.to_come_in) - Number(o.to_pay) < 0 ? "red" : undefined}
          hint={t("money.inLimboHint")}
        />
      </div>

      <section className="card mb-6 p-5">
        <h2 className="mb-4 text-sm font-semibold text-zinc-900">{t("money.chartTitle")}</h2>
        {empty ? <p className="py-10 text-center text-sm text-zinc-500">{t("money.empty")}</p> : <MoneyChart months={months} />}
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <section className="card p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-zinc-900">{t("money.whereTitle")}</h2>
            <FilterChips
              bare
              label={t("money.whereTitle")}
              options={[
                { value: "year", label: t("money.last12") },
                { value: "month", label: t("costs.thisMonthAll") },
              ]}
              value={period}
              onChange={setPeriod}
            />
          </div>
          <Categories rows={period === "year" ? o.by_category : o.by_category_this_month} />
        </section>
        <section className="card divide-y divide-zinc-100">
          <Link to="/invoices/aging" className="block p-5 hover:bg-zinc-50">
            <p className="text-xs font-medium text-zinc-500">{t("money.toComeIn")}</p>
            <p className="mt-1 text-xl font-semibold tabular-nums text-zinc-900">{formatMoney(o.to_come_in)}</p>
            <p className={`mt-0.5 text-xs ${Number(o.overdue_in) ? "text-red-600" : "text-zinc-500"}`}>
              {Number(o.overdue_in) ? t("money.overdueValue", { value: formatMoney(o.overdue_in) }) : t("money.toComeInHint")}
            </p>
          </Link>
          <Link to="/costs" className="block p-5 hover:bg-zinc-50">
            <p className="text-xs font-medium text-zinc-500">{t("costs.stillToPay")}</p>
            <p className="mt-1 text-xl font-semibold tabular-nums text-zinc-900">{formatMoney(o.to_pay)}</p>
            <p className={`mt-0.5 text-xs ${Number(o.overdue_out) ? "text-red-600" : "text-zinc-500"}`}>
              {Number(o.overdue_out) ? t("money.overdueValue", { value: formatMoney(o.overdue_out) }) : t("costs.allDates")}
            </p>
          </Link>
        </section>
      </div>

      <p className="mt-6 text-xs text-zinc-500">{t("costs.notAccounting")}</p>
    </>
  );
}
