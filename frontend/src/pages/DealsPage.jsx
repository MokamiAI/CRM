import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import apiClient from "../services/apiClient";
import { useCustomerMap, useDeals, useTeamMap } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import DealFormSheet from "../components/DealFormSheet";
import Sheet from "../components/Sheet";
import { NextActivityBadge, RowEditButton, STAGES, dueState, industryLabel } from "../components/crm";
import { Avatar, Button, ErrorState, Field, FilterChips, PageHeader, PlusIcon, Tooltip } from "../components/ui";
import { errorMessage, formatMoney, formatShortDate } from "../utils/format";
import { celebrate } from "../utils/motion";

// Pipedrive's ordering: what needs attention floats to the top of each
// column. Overdue, then due today, then deals with nothing planned (going
// cold), then deals whose next step is safely in the future.
function urgency(deal) {
  const next = deal.next_activity;
  if (!next) return [2, ""];
  const state = dueState(next.due_date);
  return [state === "overdue" ? 0 : state === "today" ? 1 : 3, next.due_date];
}

function byUrgency(a, b) {
  const [ua, da] = urgency(a);
  const [ub, db] = urgency(b);
  return ua - ub || da.localeCompare(db);
}

const sum = (deals) => deals.reduce((total, d) => total + Number(d.value), 0);

export default function DealsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const [scope, setScope] = useState("all");
  // Board or list: remembered per browser (a convenience, so storage
  // failures in private mode just fall back to the board).
  const [view, setView] = useState(() => {
    try {
      return localStorage.getItem("deals-view") ?? "board";
    } catch {
      return "board";
    }
  });
  const changeView = (next) => {
    setView(next);
    try {
      localStorage.setItem("deals-view", next);
    } catch {
      /* ignore */
    }
  };
  const params = { status: "open", ...(scope === "mine" && { mine: true }) };
  const { data: deals = [], isLoading, isError, refetch } = useDeals(params);
  const customers = useCustomerMap();
  const team = useTeamMap();
  const queryClient = useQueryClient();

  // ?new=1 (from the command palette) opens the new-deal form straight away.
  const [searchParams, setSearchParams] = useSearchParams();
  const [creating, setCreating] = useState(() => (searchParams.get("new") ? "lead" : null)); // stage to create in
  const [dragId, setDragId] = useState(null); // drives rendering (dimmed card, drop zones)
  // The handlers read the ref, not the state: dragover/drop can fire before
  // React has re-rendered with the new state, which would drop nothing.
  const dragRef = useRef(null);
  const [overStage, setOverStage] = useState(null);
  const [losing, setLosing] = useState(null);
  // The card that just moved columns plays a one-off landing animation.
  const [landedId, setLandedId] = useState(null);
  useEffect(() => {
    if (!landedId) return;
    const timer = setTimeout(() => setLandedId(null), 400);
    return () => clearTimeout(timer);
  }, [landedId]);
  const [lostReason, setLostReason] = useState("");

  const move = useMutation({
    mutationFn: ({ id, stage, lost_reason }) => apiClient.patch(`/deals/${id}`, { stage, ...(lost_reason && { lost_reason }) }),
    // Optimistic: the card lands where it was dropped immediately; a
    // failure snaps it back when the board refetches.
    onMutate: async ({ id, stage }) => {
      await queryClient.cancelQueries({ queryKey: ["deals", params] });
      const previous = queryClient.getQueryData(["deals", params]);
      queryClient.setQueryData(["deals", params], (old = []) =>
        stage === "won" || stage === "lost" ? old.filter((d) => d.id !== id) : old.map((d) => (d.id === id ? { ...d, stage } : d))
      );
      return { previous };
    },
    onError: (error, _vars, context) => {
      queryClient.setQueryData(["deals", params], context?.previous);
      toast.error(errorMessage(error));
    },
    onSuccess: (_res, { stage }) => {
      if (stage === "won") toast.success(i18n.t("deals.wonToast"), { description: i18n.t("deals.wonToastDetail") });
      if (stage === "lost") toast(i18n.t("deals.lostToast"));
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["deals"] });
      queryClient.invalidateQueries({ queryKey: ["timeline"] });
    },
  });

  function drop(stage, target) {
    const deal = deals.find((d) => d.id === dragRef.current);
    dragRef.current = null;
    setDragId(null);
    setOverStage(null);
    if (!deal || deal.stage === stage) return;
    if (stage === "lost") {
      setLostReason("");
      setLosing(deal);
      return;
    }
    if (stage === "won") celebrate(target);
    else setLandedId(deal.id);
    move.mutate({ id: deal.id, stage });
  }

  const dropProps = (stage) => ({
    onDragOver: (event) => {
      if (!dragRef.current) return;
      event.preventDefault();
      if (overStage !== stage) setOverStage(stage);
    },
    onDragLeave: (event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setOverStage(null);
    },
    onDrop: (event) => {
      event.preventDefault();
      drop(stage, event.currentTarget);
    },
  });

  const openTotal = sum(deals);

  return (
    <>
      <PageHeader
        title={t("nav.deals")}
        subtitle={isLoading ? undefined : t("deals.subtitle", { count: deals.length, amount: formatMoney(openTotal) })}
        actions={
          canWrite && (
            <Button onClick={() => setCreating("lead")}>
              <PlusIcon className="h-4 w-4" /> {t("dashboard.newDeal")}
            </Button>
          )
        }
      />
      <div className="flex flex-wrap items-start justify-between gap-x-3">
        <FilterChips
          options={[
            { value: "all", label: t("deals.everyones") },
            { value: "mine", label: t("deals.mine") },
          ]}
          value={scope}
          onChange={setScope}
        />
        <FilterChips
          options={[
            { value: "board", label: t("dashboard.board") },
            { value: "list", label: t("deals.list") },
          ]}
          value={view}
          onChange={changeView}
        />
      </div>

      {isError ? (
        <ErrorState onRetry={refetch} />
      ) : view === "list" ? (
        <DealTable deals={[...deals].sort(byUrgency)} customers={customers} team={team} loading={isLoading} />
      ) : (
        // Phones: one column per screen, swiped with native scroll snap.
        // md+: all four stages side by side.
        <div className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-4 [scrollbar-width:none] md:mx-0 md:grid md:grid-cols-4 md:overflow-visible md:px-0">
          {STAGES.map((stage, stageIndex) => {
            const column = deals.filter((d) => d.stage === stage.value).sort(byUrgency);
            const isOver = overStage === stage.value;
            return (
              <section
                key={stage.value}
                {...dropProps(stage.value)}
                className={`flex w-[85%] shrink-0 snap-start flex-col rounded-xl p-2 transition-colors duration-150 md:w-auto ${
                  isOver ? "bg-zinc-200/70" : "bg-zinc-100/70"
                }`}
              >
                {/* This stage's slice of one continuous spectrum: across the
                    four columns it reads as progress, violet through to rose. */}
                <span
                  className="spectrum-slice mx-2 mt-1 block h-[3px] rounded-full"
                  style={{ "--slices": STAGES.length, "--slice": stageIndex }}
                  aria-hidden="true"
                />
                <header className="flex items-start justify-between gap-2 px-2 pb-2.5 pt-2">
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold text-zinc-900">
                      {stage.label} <span className="font-normal text-zinc-400">{column.length}</span>
                    </h2>
                    <p className="text-xs text-zinc-500">{formatMoney(sum(column))}</p>
                  </div>
                  {canWrite && (
                    <Tooltip label={`New deal in ${stage.label}`} side="top-end">
                      <button
                        type="button"
                        onClick={() => setCreating(stage.value)}
                        aria-label={t("deals.newInStage", { stage: stage.label })}
                        className="pressable rounded-md p-1 text-zinc-400 hover:bg-white hover:text-zinc-700"
                      >
                        <PlusIcon className="h-4 w-4" />
                      </button>
                    </Tooltip>
                  )}
                </header>
                <div className="flex min-h-[6rem] flex-1 flex-col gap-2">
                  {isLoading
                    ? [0, 1].map((i) => <div key={i} className="h-24 animate-pulse rounded-lg bg-white/70" />)
                    : column.map((deal) => (
                        <DealCard
                          key={deal.id}
                          deal={deal}
                          customer={customers.get(deal.customer_id)}
                          owner={team.get(deal.owner_id)}
                          dragging={dragId === deal.id}
                          landed={landedId === deal.id}
                          draggable={canWrite}
                          onDragStart={() => {
                            dragRef.current = deal.id;
                            setDragId(deal.id);
                          }}
                          onDragEnd={() => {
                            dragRef.current = null;
                            setDragId(null);
                            setOverStage(null);
                          }}
                        />
                      ))}
                  {!isLoading && column.length === 0 && (
                    <p className="rounded-lg border border-dashed border-zinc-300 px-3 py-6 text-center text-xs text-zinc-400">
                      {dragId ? t("deals.dropHere") : t("deals.noDeals")}
                    </p>
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}

      {/* Outcome drop zones, shown only while a card is being dragged. */}
      {dragId && (
        <div className="pointer-events-none fixed inset-x-0 bottom-6 z-30 flex justify-center gap-3 px-4 md:pl-60">
          {[
            ["won", "bg-emerald-600"],
            ["lost", "bg-red-600"],
          ].map(([stage, bg]) => (
            <div
              key={stage}
              {...dropProps(stage)}
              className={`pointer-events-auto flex h-14 w-40 items-center justify-center rounded-xl text-sm font-semibold text-white shadow-pop transition-transform duration-150 ${bg} ${
                overStage === stage ? "scale-105" : ""
              }`}
            >
              {t(`stage.${stage}`)}
            </div>
          ))}
        </div>
      )}

      <DealFormSheet
        open={creating !== null}
        onClose={() => {
          setCreating(null);
          if (searchParams.get("new")) setSearchParams({}, { replace: true });
        }}
        deal={null}
        initialStage={creating ?? "lead"}
      />

      <Sheet
        open={losing !== null}
        onClose={() => setLosing(null)}
        title={t("deals.markLostTitle")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setLosing(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                move.mutate({ id: losing.id, stage: "lost", lost_reason: lostReason || null });
                setLosing(null);
              }}
            >
              {t("deals.markLost")}
            </Button>
          </>
        }
      >
        <p className="mb-4 text-sm text-zinc-600">{losing?.title}</p>
        <Field label={t("deals.lostReason")} hint={t("deals.lostReasonHint")}>
          <input className="input" value={lostReason} onChange={(e) => setLostReason(e.target.value)} placeholder={t("deals.lostReasonPlaceholder")} />
        </Field>
      </Sheet>
    </>
  );
}

function DealCard({ deal, customer, owner, dragging, landed, draggable, onDragStart, onDragEnd }) {
  return (
    <Link
      to={`/deals/${deal.id}`}
      draggable={draggable}
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = "move";
        onDragStart();
      }}
      onDragEnd={onDragEnd}
      className={`block rounded-lg border border-zinc-200/80 bg-white p-3 shadow-xs transition-[box-shadow,opacity] duration-150 hover:shadow-card ${
        dragging ? "opacity-40" : ""
      } ${landed ? "card-land" : ""}`}
    >
      <p className="text-sm font-medium leading-snug text-zinc-900">{deal.title}</p>
      <p className="mt-0.5 truncate text-xs text-zinc-500">{customer?.name ?? "…"}</p>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-zinc-900">{formatMoney(deal.value)}</span>
        {owner && <Avatar name={owner.full_name} size="sm" />}
      </div>
      <div className="mt-2 border-t border-zinc-100 pt-2">
        <NextActivityBadge activity={deal.next_activity} />
      </div>
    </Link>
  );
}

/** The same deals as a table: the view for scanning, sorting by eye and
    comparing values, where the board is for moving things along. */
function DealTable({ deals, customers, team, loading }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [editing, setEditing] = useState(null);
  if (loading) return <div className="card h-48 animate-pulse" />;
  return (
    <div className="card overflow-hidden">
      <DealFormSheet open={Boolean(editing)} onClose={() => setEditing(null)} deal={editing} />
      <table className="hidden w-full md:table">
        <thead className="table-head">
          <tr>
            <th>{t("deals.col.deal")}</th>
            <th>{t("deals.col.stage")}</th>
            <th className="text-right">{t("deals.col.value")}</th>
            <th>{t("deals.col.industry")}</th>
            <th>{t("deals.col.owner")}</th>
            <th>{t("deals.col.expectedClose")}</th>
            <th>{t("deals.col.nextStep")}</th>
            <th className="w-12"><span className="sr-only">{t("common.edit")}</span></th>
          </tr>
        </thead>
        <tbody>
          {deals.map((deal) => {
            const stageIndex = STAGES.findIndex((s) => s.value === deal.stage);
            const owner = team.get(deal.owner_id);
            return (
              <tr key={deal.id} className="table-row" onClick={() => navigate(`/deals/${deal.id}`)}>
                <td>
                  <Link to={`/deals/${deal.id}`} onClick={(e) => e.stopPropagation()} className="font-medium text-zinc-900 hover:underline">
                    {deal.title}
                  </Link>
                  <p className="text-xs text-zinc-500">{customers.get(deal.customer_id)?.name ?? "…"}</p>
                </td>
                <td>
                  <span className="inline-flex items-center gap-2 text-zinc-700">
                    {/* The stage's spectrum slice, as on the board's column bar. */}
                    <span
                      className="spectrum-slice h-2 w-2 rounded-full"
                      style={{ "--slices": STAGES.length, "--slice": stageIndex }}
                      aria-hidden="true"
                    />
                    {STAGES[stageIndex]?.label}
                  </span>
                </td>
                <td className="whitespace-nowrap text-right font-medium tabular-nums text-zinc-900">{formatMoney(deal.value)}</td>
                <td className="whitespace-nowrap text-zinc-600">{industryLabel(deal.industry) || "—"}</td>
                <td>
                  {owner && (
                    <span className="inline-flex items-center gap-2 text-zinc-600">
                      <Avatar name={owner.full_name} size="sm" />
                      {owner.full_name.split(" ")[0]}
                    </span>
                  )}
                </td>
                <td className="whitespace-nowrap text-zinc-500">{deal.expected_close_date ? formatShortDate(deal.expected_close_date) : "—"}</td>
                <td>
                  <NextActivityBadge activity={deal.next_activity} />
                </td>
                <td className="text-right">{user?.role !== "viewer" && <RowEditButton label={t("edit.deal", { title: deal.title })} onClick={() => setEditing(deal)} />}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <ul className="divide-y divide-zinc-100 md:hidden">
        {deals.map((deal) => (
          <li key={deal.id}>
            <Link to={`/deals/${deal.id}`} className="flex items-center justify-between gap-3 px-4 py-3.5 active:bg-zinc-50">
              <div className="min-w-0">
                <p className="truncate font-medium text-zinc-900">{deal.title}</p>
                <p className="truncate text-[13px] text-zinc-500">
                  {customers.get(deal.customer_id)?.name ?? "…"} · {STAGES.find((s) => s.value === deal.stage)?.label}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <span className="text-sm font-medium tabular-nums text-zinc-900">{formatMoney(deal.value)}</span>
                <NextActivityBadge activity={deal.next_activity} />
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {!deals.length && <p className="px-5 py-8 text-center text-sm text-zinc-500">{t("deals.noOpenDeals")}</p>}
    </div>
  );
}
