import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useActivities, useCustomerMap, useInvoices, useQuotes, useReportSummary } from "../hooks/useApi";
import GetStarted from "../components/GetStarted";
import { useAuth } from "../context/AuthContext";
import i18n from "../i18n";
import { useToggleActivity } from "../components/crm";
import { PlanBanner } from "../components/Billing";
import { ButtonLink, ErrorState, PageHeader, PlusIcon, StatusBadge } from "../components/ui";
import { Link } from "react-router-dom";
import {
  GoalCard,
  KpiCard,
  OwedList,
  Panel,
  PipelineSummary,
  QuickActions,
  RevenueChart,
  UpcomingList,
  ViewAll,
} from "../components/dashboard";
import { formatMoney, formatMoneyWhole, formatShortDate, todayISO } from "../utils/format";

function greeting() {
  const hour = new Date().getHours();
  return i18n.t(hour < 12 ? "dashboard.morning" : hour < 18 ? "dashboard.afternoon" : "dashboard.evening");
}

const RANGES = [3, 6, 12];
const OPEN_STAGES = ["lead", "qualified", "proposal", "negotiation"];

/** Skeleton in the dashboard's own shape, so nothing jumps when it loads. */
function DashboardSkeleton() {
  const block = "animate-pulse rounded-2xl bg-slate-200/60 motion-reduce:animate-none";
  return (
    <div className="space-y-5" aria-busy="true">
      <div className={`${block} h-24`} />
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={`${block} h-24`} />
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-3">
        <div className={`${block} h-80 xl:col-span-2`} />
        <div className={`${block} h-80`} />
      </div>
    </div>
  );
}

/** Month-on-month change, only when last month had something to compare. */
function change(series) {
  const now = Number(series.at(-1)?.total ?? 0);
  const before = Number(series.at(-2)?.total ?? 0);
  return before > 0 ? (now - before) / before : null;
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data: s, isLoading, isError, refetch } = useReportSummary();
  const { data: overdueActs = [] } = useActivities({ scope: "overdue", mine: true });
  const { data: todayActs = [] } = useActivities({ scope: "today", mine: true });
  const { data: nextActs = [] } = useActivities({ scope: "upcoming", mine: true });
  // Only the rows shown: five per unpaid status, soonest due first.
  const { data: overdueInv = [] } = useInvoices({ status: "overdue", sort: "due", limit: 5 });
  const { data: sentInv = [] } = useInvoices({ status: "sent", sort: "due", limit: 5 });
  const { data: partInv = [] } = useInvoices({ status: "partially_paid", sort: "due", limit: 5 });
  const { data: sentQuotes = [] } = useQuotes({ status: "sent", limit: 4 });
  const customers = useCustomerMap();
  const toggle = useToggleActivity();
  const [range, setRange] = useState(6);
  const today = todayISO();
  const canWrite = user?.role !== "viewer";

  const owed = useMemo(
    () => [...overdueInv, ...partInv, ...sentInv].sort((a, b) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999")).slice(0, 5),
    [overdueInv, partInv, sentInv]
  );

  if (isLoading) return <DashboardSkeleton />;
  if (isError) return <ErrorState onRetry={refetch} />;

  const firstName = user?.full_name?.split(" ")[0];
  const upcoming = [...overdueActs, ...todayActs, ...nextActs].slice(0, 5);
  const months = s.invoiced_by_month.slice(-range).map((m, i, list) => ({
    month: m.month,
    invoiced: Number(m.total),
    collected: Number(s.collected_by_month.slice(-range)[i]?.total ?? 0),
    last: i === list.length - 1,
  }));
  const hasMoney = months.some((m) => m.invoiced > 0 || m.collected > 0);
  const stages = [
    ...s.pipeline.filter((p) => OPEN_STAGES.includes(p.stage)),
    { stage: "won", count: s.won_this_month.count, value: s.won_this_month.value },
  ];
  const quick = [
    { to: "/customers?new=1", icon: "plusUser", label: t("dashboard.quick.customer") },
    { to: "/deals?new=1", icon: "deals", label: t("dashboard.quick.deal") },
    { to: "/quotes/new", icon: "quote", label: t("dashboard.quick.quote") },
    { to: "/invoices/new", icon: "invoice", label: t("dashboard.quick.invoice") },
    { to: "/activities?new=1", icon: "activity", label: t("dashboard.quick.activity") },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title={
          firstName ? (
            <>
              {greeting()}, <span className="brand-text">{firstName}</span>
            </>
          ) : (
            greeting()
          )
        }
        subtitle={t("dashboard.subtitle")}
        actions={
          canWrite && (
            <>
              <ButtonLink variant="secondary" to="/deals?new=1" className="hidden sm:inline-flex">
                {t("dashboard.newDeal")}
              </ButtonLink>
              <ButtonLink to="/invoices/new">
                <PlusIcon className="h-4 w-4" /> {t("dashboard.newInvoice")}
              </ButtonLink>
            </>
          )
        }
      />

      <PlanBanner />
      <GetStarted />

      {/* The four numbers to check first, each a door to its page. */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4" data-tour="dash-kpis">
        <KpiCard
          to="/invoices"
          icon="cash"
          tone="emerald"
          label={t("dashboard.kpi.collected")}
          value={formatMoneyWhole(s.collected_by_month.at(-1).total)}
          change={change(s.collected_by_month)}
          detail={t("dashboard.kpi.thisMonth")}
          spark={s.collected_by_month.slice(-6).map((m) => Number(m.total))}
          sparkColor="#059669"
        />
        <KpiCard
          to="/invoices/aging"
          icon="invoice"
          tone="amber"
          label={t("dashboard.kpi.outstanding")}
          value={formatMoneyWhole(s.outstanding)}
          detail={Number(s.overdue) > 0 ? t("dashboard.overdueAmount", { amount: formatMoneyWhole(s.overdue) }) : t("dashboard.acrossInvoices", { count: s.open_invoice_count })}
        />
        <KpiCard
          to="/deals"
          icon="deals"
          tone="blue"
          label={t("dashboard.kpi.openDeals")}
          value={formatMoneyWhole(s.open_pipeline_value)}
          detail={t("dashboard.openDeals", { count: s.open_deal_count })}
        />
        <KpiCard
          to="/customers"
          icon="customers"
          tone="violet"
          label={t("dashboard.kpi.customers")}
          value={s.active_customers.toLocaleString(i18n.language)}
          detail={t("dashboard.kpi.newThisMonth", { count: s.new_customers_this_month })}
        />
      </div>

      <GoalCard goal={s.goal} today={today} canEdit={user?.role === "admin"} />

      <div className="grid gap-5 xl:grid-cols-3">
        {/* Left: the pipeline, then money over time. Right: what to do next. */}
        <div className="grid min-w-0 content-start gap-5 xl:col-span-2">
          <Panel
            title={t("dashboard.pipeline.title")}
            subtitle={t("dashboard.pipeline.subtitle")}
            action={<ViewAll to="/deals">{t("dashboard.viewAll")}</ViewAll>}
            bodyClass="px-4 pb-4"
            tour="dash-charts"
          >
            <PipelineSummary stages={stages} />
            {/* How well deals close; this month's wins are the green tile above. */}
            <dl className="mt-4 grid grid-cols-2 divide-x divide-slate-100 rounded-xl border border-slate-200/80 text-center">
              {[
                [t("dashboard.kpi.winRate"), s.win_rate == null ? "—" : `${Math.round(s.win_rate * 100)}%`, t("dashboard.kpi.winRateDetail")],
                [t("dashboard.kpi.avgDeal"), s.avg_won_deal == null ? "—" : formatMoneyWhole(s.avg_won_deal), t("dashboard.kpi.avgDealDetail")],
              ].map(([label, value, hint]) => (
                <div key={label} className="min-w-0 px-2 py-3">
                  <dt className="truncate text-xs font-medium text-slate-500">{label}</dt>
                  <dd className="mt-0.5 truncate text-base font-bold tabular-nums text-midnight sm:text-lg">{value}</dd>
                  <dd className="hidden truncate text-xs text-slate-500 sm:block">{hint}</dd>
                </div>
              ))}
            </dl>
          </Panel>
          <Panel
            title={t("dashboard.revenue.title")}
            subtitle={t("dashboard.revenue.subtitle")}
            action={
              <select
                className="input !h-8 !w-auto !py-0 !pl-2.5 !pr-8 !text-xs"
                value={range}
                onChange={(e) => setRange(Number(e.target.value))}
                aria-label={t("dashboard.revenue.range")}
              >
                {RANGES.map((n) => (
                  <option key={n} value={n}>
                    {t("dashboard.revenue.lastMonths", { count: n })}
                  </option>
                ))}
              </select>
            }
            bodyClass="px-5 pb-5"
          >
            {hasMoney ? <RevenueChart months={months} /> : <p className="py-10 text-center text-sm text-slate-500">{t("dashboard.revenue.empty")}</p>}
          </Panel>
          <Panel title={t("dashboard.owes.title")} action={<ViewAll to="/invoices/aging">{t("dashboard.viewAll")}</ViewAll>}>
            {owed.length ? <OwedList invoices={owed} customers={customers} today={today} /> : <p className="px-5 pb-5 text-sm text-slate-500">{t("dashboard.owes.empty")}</p>}
          </Panel>
        </div>
        <div className="grid min-w-0 content-start gap-5">
          {canWrite && (
            <Panel title={t("dashboard.quick.title")}>
              <QuickActions actions={quick} />
            </Panel>
          )}
          <Panel tour="dash-day" title={t("dashboard.upcoming.title")} action={<ViewAll to="/activities">{t("dashboard.viewAll")}</ViewAll>}>
            {upcoming.length ? (
              <UpcomingList items={upcoming} customers={customers} today={today} onToggle={(a) => toggle.mutate(a)} />
            ) : (
              <p className="px-5 pb-5 text-sm text-slate-500">{t("dashboard.upcoming.empty")}</p>
            )}
          </Panel>
          <Panel title={t("dashboard.awaitingReply")} action={<ViewAll to="/quotes">{t("dashboard.viewAll")}</ViewAll>}>
            {sentQuotes.length ? (
              <ul className="divide-y divide-slate-100">
                {sentQuotes.slice(0, 4).map((q) => (
                  <li key={q.id}>
                    <Link to={`/quotes/${q.id}`} className="flex items-center justify-between gap-3 px-5 py-3 text-sm hover:bg-slate-50">
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-midnight">{customers.get(q.customer_id)?.name ?? "…"}</span>
                        <span className="text-xs text-slate-500">
                          {q.quote_number}
                          {q.expiry_date && ` · ${t("dashboard.validUntil", { date: formatShortDate(q.expiry_date) })}`}
                        </span>
                      </span>
                      <span className="flex shrink-0 flex-col items-end gap-1">
                        <span className="font-semibold tabular-nums text-midnight">{formatMoney(q.total)}</span>
                        <StatusBadge status={q.status} />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 pb-5 text-sm text-slate-500">{t("dashboard.noQuotesWaiting")}</p>
            )}
          </Panel>
        </div>
      </div>

    </div>
  );
}
