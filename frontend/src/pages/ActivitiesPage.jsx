import MeetingCalendar from "../components/MeetingCalendar";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useActivities, useActivity, useActivityCounts, useCustomerMap, useDeals, useTeamMap } from "../hooks/useApi";
import TaskSheet from "../components/TaskSheet";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { ActivityIcon, ActivityRow, activityColor, ACTIVITY_TYPES, ComposerSheet, useToggleActivity } from "../components/crm";
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
  const canSeeEveryone = ["admin", "manager"].includes(user?.role);
  const { data: counts } = useActivityCounts();
  const [scope, setScope] = useState(() => (counts?.overdue ? "overdue" : "today"));
  const [who, setWho] = useState("mine");
  const params = { scope, ...(who === "mine" && { mine: true }), ...(who === "handed" && { handed_out: true }) };
  const team = useTeamMap();
  const [openTask, setOpenTask] = useState(null);
  const [showCalendar, setShowCalendar] = useState(false);
  const { data: all = [], isLoading, isError, refetch } = useActivities(params);
  // Calls, meetings, tasks...: one tap shows just that kind.
  const [kind, setKind] = useState("all");
  const activities = kind === "all" ? all : all.filter((a) => a.type === kind);
  const customers = useCustomerMap();
  const { data: deals = [] } = useDeals({ status: "all" });
  const dealTitles = new Map(deals.map((d) => [d.id, d.title]));
  const toggle = useToggleActivity();
  // "Log activity" from the dashboard arrives as ?new=1: open the composer once.
  const [searchParams, setSearchParams] = useSearchParams();
  const [creating, setCreating] = useState(() => canWrite && searchParams.get("new") === "1");
  // A notification links here as ?task=<id>: open that task's panel.
  const linked = searchParams.get("task");
  const { data: linkedActivity } = useActivity(linked);
  useEffect(() => {
    if (!linked) return;
    const found = activities.find((a) => a.id === linked) ?? linkedActivity;
    if (found) setOpenTask(found);
  }, [linked, activities, linkedActivity]);
  const closeTask = () => {
    setOpenTask(null);
    if (searchParams.get("task")) setSearchParams({}, { replace: true });
  };
  const closeComposer = () => {
    setCreating(false);
    if (searchParams.get("new")) setSearchParams({}, { replace: true });
  };

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
          <>
            <Button variant="secondary" onClick={() => setShowCalendar((show) => !show)}>{t(showCalendar ? "meeting.hideCalendar" : "meeting.showCalendar", showCalendar ? "Hide calendar" : "My calendar")}</Button>
            {canWrite && (
              <Button onClick={() => setCreating(true)}>
                <PlusIcon className="h-4 w-4" /> {t("activities.new")}
              </Button>
            )}
          </>
        }
      />
      {showCalendar && <MeetingCalendar />}
      <div className="md:flex md:items-start md:justify-between md:gap-3">
        <FilterChips options={options} value={scope} onChange={setScope} />
        <FilterChips
          options={[
            { value: "mine", label: t("activities.mine") },
            { value: "handed", label: t("activities.handedOut") },
            ...(canSeeEveryone ? [{ value: "all", label: t("activities.everyone") }] : []),
          ]}
          value={who}
          onChange={setWho}
        />
      </div>

      <div className="-mt-1 mb-4 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none]" role="radiogroup" aria-label={t("activities.byType")}>
        {[{ value: "all", label: t("common.all") }, ...ACTIVITY_TYPES].map((option) => {
          const count = option.value === "all" ? all.length : all.filter((a) => a.type === option.value).length;
          const on = kind === option.value;
          const color = option.value === "all" ? null : activityColor(option.value);
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => setKind(option.value)}
              className={`pressable inline-flex shrink-0 items-center gap-1.5 rounded-full py-1 pl-1.5 pr-3 text-sm font-medium ring-1 ring-inset transition-colors duration-150 ${
                on ? (color ? color.solid : "bg-zinc-900 text-white ring-zinc-900") : "bg-white text-zinc-700 ring-zinc-200 hover:bg-zinc-50"
              } ${option.value === "all" ? "pl-3" : ""}`}
            >
              {color && (
                <span className={`flex h-6 w-6 items-center justify-center rounded-full ${on ? "bg-white/20" : color.icon}`}>
                  <ActivityIcon type={option.value} className="h-3.5 w-3.5" />
                </span>
              )}
              {option.label}
              <span className={`text-xs ${on ? "text-white/80" : "text-zinc-400"}`}>{count}</span>
            </button>
          );
        })}
      </div>

      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : activities.length === 0 ? (
        all.length > 0 ? (
          <EmptyState title={t("activities.noneOfType")} action={<Button variant="secondary" onClick={() => setKind("all")}>{t("activities.showAll")}</Button>} />
        ) : (
          <EmptyState title={t(EMPTY[scope][0])} description={t(EMPTY[scope][1])} />
        )
      ) : (
        <ul className="card divide-y divide-zinc-100 overflow-hidden">
          {activities.map((activity) => (
            <ActivityRow
              key={activity.id}
              activity={activity}
              onToggle={toggle.mutate}
              onOpen={setOpenTask}
              context={
                <>
                  {activity.owner_id && activity.owner_id !== user?.id && (
                    <span className="font-medium text-zinc-600">{t("activities.forPerson", { name: team.get(activity.owner_id)?.full_name?.split(" ")[0] ?? "…" })}</span>
                  )}
                  {activity.owner_id === user?.id && activity.created_by && activity.created_by !== user?.id && (
                    <span className="font-medium text-zinc-600">{t("activities.fromPerson", { name: team.get(activity.created_by)?.full_name?.split(" ")[0] ?? "…" })}</span>
                  )}
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

      <ComposerSheet open={creating} onClose={closeComposer} mode="activity" />
      <TaskSheet
        activity={openTask && (activities.find((a) => a.id === openTask.id) ?? openTask)}
        open={Boolean(openTask)}
        onClose={closeTask}
      />
    </>
  );
}
