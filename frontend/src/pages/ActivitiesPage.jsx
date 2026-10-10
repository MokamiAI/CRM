import { useState } from "react";
import { Link } from "react-router-dom";
import { useActivities, useActivityCounts, useCustomerMap, useDeals } from "../hooks/useApi";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { ActivityRow, ComposerSheet, useToggleActivity } from "../components/crm";
import { Button, EmptyState, ErrorState, FilterChips, ListSkeleton, PageHeader, PlusIcon } from "../components/ui";

const SCOPES = [
  { value: "overdue" },
  { value: "today" },
  { value: "upcoming" },
  { value: "done" },
];

const EMPTY = {
  overdue: ["activities.empty.overdue", "activities.empty.overdueHint"],
  today: ["activities.empty.today", "activities.empty.todayHint"],
  upcoming: ["activities.empty.upcoming", "activities.empty.upcomingHint"],
  done: ["activities.empty.done", "activities.empty.doneHint"],
};

/**
 * The daily work queue, the screen sales tools are built around: what's
 * late, what's for today, what's next. Ticking an item off is one tap and
 * deliberately un-animated beyond the checkbox: it's done dozens of times a day.
 */
export default function ActivitiesPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const { data: counts } = useActivityCounts();
  const [scope, setScope] = useState(() => (counts?.overdue ? "overdue" : "today"));
  const [who, setWho] = useState("mine");
  const params = { scope, ...(who === "mine" && { mine: true }) };
  const { data: activities = [], isLoading, isError, refetch } = useActivities(params);
  const customers = useCustomerMap();
  const { data: deals = [] } = useDeals({ status: "all" });
  const dealTitles = new Map(deals.map((d) => [d.id, d.title]));
  const toggle = useToggleActivity();
  const [creating, setCreating] = useState(false);

  const options = SCOPES.map((s) => ({
    ...s,
    label: who === "mine" && counts?.[s.value] ? `${t(`activities.scope.${s.value}`)} · ${counts[s.value]}` : t(`activities.scope.${s.value}`),
  }));

  return (
    <>
      <PageHeader
        title={t("nav.activities")}
        subtitle={t("activities.subtitle")}
        actions={
          canWrite && (
            <Button onClick={() => setCreating(true)}>
              <PlusIcon className="h-4 w-4" /> {t("activities.new")}
            </Button>
          )
        }
      />
      <div className="md:flex md:items-start md:justify-between md:gap-3">
        <FilterChips options={options} value={scope} onChange={setScope} />
        <FilterChips
          options={[
            { value: "mine", label: t("activities.mine") },
            { value: "all", label: t("activities.everyone") },
          ]}
          value={who}
          onChange={setWho}
        />
      </div>

      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : activities.length === 0 ? (
        <EmptyState title={t(EMPTY[scope][0])} description={t(EMPTY[scope][1])} />
      ) : (
        <ul className="card divide-y divide-zinc-100 overflow-hidden">
          {activities.map((activity) => (
            <ActivityRow
              key={activity.id}
              activity={activity}
              onToggle={toggle.mutate}
              context={
                <>
                  {activity.deal_id && (
                    <Link to={`/deals/${activity.deal_id}`} className="font-medium text-zinc-700 hover:underline">
                      {dealTitles.get(activity.deal_id) ?? t("palette.kind.deal")}
                    </Link>
                  )}
                  {activity.customer_id && (
                    <Link to={`/customers/${activity.customer_id}`} className="hover:underline">
                      {customers.get(activity.customer_id)?.name ?? t("palette.kind.customer")}
                    </Link>
                  )}
                </>
              }
            />
          ))}
        </ul>
      )}

      <ComposerSheet open={creating} onClose={() => setCreating(false)} mode="activity" />
    </>
  );
}
