import { Link } from "react-router-dom";
import { useActivities, useCustomerMap, useInvoices, useQuotes, useReportSummary, useTeamMap } from "../hooks/useApi";
import { useTranslation } from "react-i18next";
import GetStarted from "../components/GetStarted";
import { useAuth } from "../context/AuthContext";
import i18n from "../i18n";
import { BarList, ColumnChart } from "../components/charts";
import { ActivityIcon, ActivityRow, STAGE_LABELS, useToggleActivity } from "../components/crm";
import { PlanBanner } from "../components/Billing";
import { Avatar, ButtonLink, ErrorState, ListSkeleton, PageHeader, PlusIcon, StatusBadge } from "../components/ui";
import { formatMoney, formatShortDate } from "../utils/format";

function greeting() {
  const hour = new Date().getHours();
  return i18n.t(hour < 12 ? "dashboard.morning" : hour < 18 ? "dashboard.afternoon" : "dashboard.evening");
}

function Panel({ title, action, children, className = "", tour }) {
  return (
    <section className={`card flex min-w-0 flex-col ${className}`} data-tour={tour}>
      <div className="flex items-center justify-between gap-2 border-b border-zinc-100 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-zinc-900">{title}</h2>
        {action}
      </div>
      <div className="flex-1">{children}</div>
    </section>
  );
}

// Feed entries are phrased in the user's language from kind + params.
function feedTitle(item) {
  const t = i18n.t.bind(i18n);
  if (item.kind === "activity") return t("feed.activityDone", { type: t(`activityType.${item.params?.type ?? "task"}`) });
  if (item.kind === "payment") return t("feed.payment");
  if (item.kind === "note") return t("feed.note");
  if (item.kind === "deal_won") return t("feed.dealWon");
  if (item.kind === "deal_lost") return t("feed.dealLost");
  return item.title;
}

function feedDetail(item) {
  if (item.kind === "payment" && item.params?.amount) return `${item.params.number} · ${formatMoney(item.params.amount)}`;
  return item.detail;
}

const PanelLink = ({ to, children }) => (
  <Link to={to} className="text-xs font-medium text-zinc-500 hover:text-zinc-900">
    {children} →
  </Link>
);

// Stat tile: label, value (proportional figures at display size), detail.
function Kpi({ label, value, detail, to }) {
  return (
    <Link to={to} className="card block px-5 py-4 transition-shadow duration-150 hover:shadow-pop">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1.5 text-xl font-semibold tracking-tight text-zinc-900 sm:text-2xl">{value}</p>
      <p className="mt-0.5 text-xs text-zinc-500">{detail}</p>
    </Link>
  );
}

const FEED_ICON = { note: "note", activity: "task", payment: "task", deal_won: "deadline", deal_lost: "deadline" };
const FEED_TINT = {
  note: "bg-amber-50 text-amber-700",
  activity: "bg-sky-50 text-sky-700",
  payment: "bg-emerald-50 text-emerald-700",
  deal_won: "bg-violet-50 text-violet-700",
  deal_lost: "bg-zinc-100 text-zinc-500",
};

function feedLink(item) {
  if (item.invoice_id) return `/invoices/${item.invoice_id}`;
  if (item.deal_id) return `/deals/${item.deal_id}`;
  if (item.customer_id) return `/customers/${item.customer_id}`;
  return null;
}

function ago(iso) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 60) return `${Math.max(minutes, 1)}m`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)}h`;
  return `${Math.round(minutes / (60 * 24))}d`;
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data: s, isLoading, isError, refetch } = useReportSummary();
  const { data: overdue = [] } = useInvoices({ status: "overdue" });
  const { data: sentQuotes = [] } = useQuotes({ status: "sent" });
  const { data: overdueActs = [] } = useActivities({ scope: "overdue", mine: true });
  const { data: todayActs = [] } = useActivities({ scope: "today", mine: true });
  const customers = useCustomerMap();
  const team = useTeamMap();
  const toggle = useToggleActivity();

  if (isLoading) return <ListSkeleton rows={5} />;
  if (isError) return <ErrorState onRetry={refetch} />;

  const firstName = user?.full_name?.split(" ")[0];
  const share = Number(s.outstanding) > 0 ? Number(s.overdue) / Number(s.outstanding) : 0;
  const thisMonth = s.collected_by_month.at(-1);
  const myDay = [...overdueActs, ...todayActs];

  return (
    <div className="space-y-6">
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
          user?.role !== "viewer" && (
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

      {/* KPI strip: the four numbers a sales lead checks first. */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-tour="dash-kpis">
        <Kpi label={t("dashboard.kpi.pipeline")} value={formatMoney(s.open_pipeline_value)} detail={t("dashboard.openDeals", { count: s.open_deal_count })} to="/deals" />
        <Kpi label={t("dashboard.kpi.won")} value={formatMoney(s.won_this_month.value)} detail={t("dashboard.deals", { count: s.won_this_month.count })} to="/deals" />
        <Kpi label={t("dashboard.kpi.winRate")} value={s.win_rate == null ? "—" : `${Math.round(s.win_rate * 100)}%`} detail={t("dashboard.kpi.winRateDetail")} to="/deals" />
        <Kpi label={t("dashboard.kpi.avgDeal")} value={s.avg_won_deal == null ? "—" : formatMoney(s.avg_won_deal)} detail={t("dashboard.kpi.avgDealDetail")} to="/deals" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3" data-tour="dash-charts">
        <Panel title={t("dashboard.pipelineByStage")} action={<PanelLink to="/deals">{t("dashboard.board")}</PanelLink>}>
          <div className="px-5 py-5">
            <BarList
              ariaLabel={t("dashboard.pipelineByStageAria")}
              rows={s.pipeline.map((p) => ({ label: STAGE_LABELS[p.stage], value: p.value, detail: t("dashboard.deals", { count: p.count }) }))}
            />
          </div>
        </Panel>

        <Panel title={t("dashboard.cashCollected")} action={<span className="text-xs text-zinc-500">{t("dashboard.last6Months")}</span>}>
          <div className="px-5 pb-4 pt-6">
            <ColumnChart ariaLabel={t("dashboard.cashCollectedAria")} data={s.collected_by_month} />
            <p className="mt-3 text-xs text-zinc-500">{t("dashboard.collectedThisMonth", { amount: formatMoney(thisMonth.total) })}</p>
          </div>
        </Panel>

        <Panel title={t("dashboard.receivables")} action={<PanelLink to="/invoices">{t("nav.invoices")}</PanelLink>}>
          <div className="relative overflow-hidden px-5 pt-5">
            <span className="pointer-events-none absolute -right-16 -top-20 h-48 w-64 rounded-full bg-violet-400/15 blur-3xl" aria-hidden="true" />
            <p className="relative text-xs font-medium uppercase tracking-wide text-zinc-500">{t("dashboard.outstanding")}</p>
            <p className="relative mt-1 text-4xl font-semibold tracking-tight text-zinc-900">{formatMoney(s.outstanding)}</p>
            <p className="relative mt-0.5 text-xs text-zinc-500">{t("dashboard.acrossInvoices", { count: s.open_invoice_count })}</p>
            {/* Meter: severity fill on a lighter step of the same ramp, with words. */}
            <div
              className="mt-4 flex h-2 overflow-hidden rounded-full bg-red-100"
              role="meter"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(share * 100)}
              aria-label={t("dashboard.overdueShare")}
            >
              <div className="rounded-full bg-red-500" style={{ width: `${Math.max(share * 100, share > 0 ? 2 : 0)}%` }} />
            </div>
            <p className="mt-2 flex items-center justify-between text-xs">
              <span className="inline-flex items-center gap-1.5 text-zinc-700">
                <span className="h-2 w-2 rounded-full bg-red-500" aria-hidden="true" />
                {t("dashboard.overdueAmount", { amount: formatMoney(s.overdue) })}
              </span>
              <span className="text-zinc-500">{Math.round(share * 100)}%</span>
            </p>
          </div>
          <ul className="mt-4 divide-y divide-zinc-100 border-t border-zinc-100">
            {overdue.slice(0, 3).map((inv) => (
              <li key={inv.id}>
                <Link to={`/invoices/${inv.id}`} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm hover:bg-zinc-50">
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-zinc-900">{customers.get(inv.customer_id)?.name ?? "…"}</span>
                    <span className="text-xs text-zinc-500">
                      {inv.invoice_number} · {t("dashboard.dueOn", { date: formatShortDate(inv.due_date) })}
                    </span>
                  </span>
                  <span className="shrink-0 tabular-nums text-zinc-900">{formatMoney(Number(inv.total) - Number(inv.amount_paid))}</span>
                </Link>
              </li>
            ))}
            {!overdue.length && <li className="px-5 py-3 text-sm text-zinc-500">{t("dashboard.nothingOverdue")}</li>}
          </ul>
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title={t("dashboard.topDeals")} action={<PanelLink to="/deals">{t("dashboard.allDeals")}</PanelLink>} className="lg:col-span-2">
          <table className="w-full">
            <thead className="table-head">
              <tr>
                <th>{t("deals.col.deal")}</th>
                <th className="hidden sm:table-cell">{t("deals.col.stage")}</th>
                <th className="hidden md:table-cell">{t("deals.col.owner")}</th>
                <th className="text-right">{t("deals.col.value")}</th>
              </tr>
            </thead>
            <tbody>
              {s.top_deals.map((d) => {
                const owner = team.get(d.owner_id);
                return (
                  <tr key={d.id} className="table-row">
                    <td>
                      <Link to={`/deals/${d.id}`} className="font-medium text-zinc-900 hover:underline">
                        {d.title}
                      </Link>
                      <p className="text-xs text-zinc-500">{d.customer_name}</p>
                    </td>
                    <td className="hidden text-zinc-600 sm:table-cell">{STAGE_LABELS[d.stage]}</td>
                    <td className="hidden md:table-cell">
                      {owner && (
                        <span className="inline-flex items-center gap-2 text-zinc-600">
                          <Avatar name={owner.full_name} size="sm" />
                          {owner.full_name.split(" ")[0]}
                        </span>
                      )}
                    </td>
                    <td className="whitespace-nowrap text-right font-medium tabular-nums text-zinc-900">{formatMoney(d.value)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Panel>

        <Panel tour="dash-day" title={t("dashboard.yourDay")} action={<PanelLink to="/activities">{t("nav.activities")}</PanelLink>}>
          {myDay.length ? (
            <ul className="divide-y divide-zinc-100">
              {myDay.slice(0, 5).map((a) => (
                <ActivityRow
                  key={a.id}
                  activity={a}
                  onToggle={toggle.mutate}
                  context={
                    a.customer_id && (
                      <Link to={a.deal_id ? `/deals/${a.deal_id}` : `/customers/${a.customer_id}`} className="hover:underline">
                        {customers.get(a.customer_id)?.name}
                      </Link>
                    )
                  }
                />
              ))}
            </ul>
          ) : (
            <p className="px-5 py-4 text-sm text-zinc-500">{t("dashboard.nothingToday")}</p>
          )}
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title={t("dashboard.recentActivity")} className="lg:col-span-2">
          <ul className="divide-y divide-zinc-100">
            {s.recent_activity.map((item, i) => {
              const href = feedLink(item);
              const actor = team.get(item.actor_id)?.full_name;
              return (
                <li key={`${item.kind}-${i}`} className="flex items-start gap-3 px-5 py-3">
                  <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${FEED_TINT[item.kind] ?? FEED_TINT.activity}`}>
                    <ActivityIcon type={FEED_ICON[item.kind] ?? "task"} className="h-3.5 w-3.5" />
                  </span>
                  <div className="min-w-0 flex-1 text-sm">
                    <p className="text-zinc-900">
                      <span className="font-medium">{feedTitle(item)}</span>
                      {item.customer_name && (
                        <>
                          {" · "}
                          <Link to={`/customers/${item.customer_id}`} className="text-zinc-600 hover:underline">
                            {item.customer_name}
                          </Link>
                        </>
                      )}
                    </p>
                    {feedDetail(item) &&
                      (href ? (
                        <Link to={href} className="block truncate text-zinc-500 hover:text-zinc-800">
                          {feedDetail(item)}
                        </Link>
                      ) : (
                        <p className="truncate text-zinc-500">{feedDetail(item)}</p>
                      ))}
                  </div>
                  <span className="shrink-0 text-right text-xs text-zinc-400">
                    {ago(item.at)}
                    {actor && <span className="block">{actor.split(" ")[0]}</span>}
                  </span>
                </li>
              );
            })}
          </ul>
        </Panel>

        <Panel title={t("dashboard.awaitingReply")} action={<PanelLink to="/quotes">{t("nav.quotes")}</PanelLink>}>
          {sentQuotes.length ? (
            <ul className="divide-y divide-zinc-100">
              {sentQuotes.slice(0, 5).map((q) => (
                <li key={q.id}>
                  <Link to={`/quotes/${q.id}`} className="flex items-center justify-between gap-3 px-5 py-3 text-sm hover:bg-zinc-50">
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-zinc-900">{customers.get(q.customer_id)?.name ?? "…"}</span>
                      <span className="text-xs text-zinc-500">
                        {q.quote_number}
                        {q.expiry_date && ` · ${t("dashboard.validUntil", { date: formatShortDate(q.expiry_date) })}`}
                      </span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-1">
                      <span className="tabular-nums text-zinc-900">{formatMoney(q.total)}</span>
                      <StatusBadge status={q.status} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 py-4 text-sm text-zinc-500">{t("dashboard.noQuotesWaiting")}</p>
          )}
        </Panel>
      </div>
    </div>
  );
}
