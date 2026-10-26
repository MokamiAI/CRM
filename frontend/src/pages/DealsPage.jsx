import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useCustomerMap, useDeals, useTeamMap } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import DealFormSheet from "../components/DealFormSheet";
import Sheet from "../components/Sheet";
import { McemReport } from "../components/McemProgress";
import { ComposerSheet, JourneyBar, NextActivityBadge, PRIORITY_RANK, PriorityBadge, RowEditButton, STAGES, dueState, industryLabel, journeyPercent } from "../components/crm";
import { Avatar, Button, ErrorState, Field, FilterChips, PageHeader, PlusIcon, Tooltip } from "../components/ui";
import { errorMessage, formatMoney, formatMoneyFit, formatShortDate } from "../utils/format";
import ImportExportButtons from "../components/ImportExport";

// Pipedrive's ordering: what needs attention floats to the top of each
// column. Overdue, then due today, then deals with nothing planned (going
// cold), then deals whose next step is safely in the future.
function urgency(deal) {
  const next = deal.next_activity;
  if (!next) return [2, ""];
  const state = dueState(next.due_date);
  return [state === "overdue" ? 0 : state === "today" ? 1 : 3, next.due_date];
}

// High-priority deals lead each column; within a priority, urgency decides.
function byUrgency(a, b) {
  const rank = (d) => PRIORITY_RANK[d.priority] ?? 1;
  const [ua, da] = urgency(a);
  const [ub, db] = urgency(b);
  return rank(a) - rank(b) || ua - ub || da.localeCompare(db);
}

const sum = (deals) => deals.reduce((total, d) => total + Number(d.value), 0);

// Older MCEM accounts remain visible for ongoing customer success.
const CLOSED_DAYS = 90;
const MCEM_PHASES = [
  ["Listen and Consult", "Understand the customer problem and agree the outcome."],
  ["Inspire and Design", "Agree the solution and how success will be measured."],
  ["Empower and Achieve", "Validate the solution, review the proposal and secure agreement."],
  ["Realize Value", "Deliver, support adoption and measure results."],
  ["Manage and Optimize", "Review value, prepare renewals and identify new needs."],
];
const isOpen = (deal) => deal.stage !== "won" && deal.stage !== "lost";
const recentlyClosed = (deal) => Boolean(deal.closed_at) && Date.now() - new Date(deal.closed_at).getTime() <= CLOSED_DAYS * 86400000;
const byClosed = (a, b) => (b.closed_at ?? "").localeCompare(a.closed_at ?? "");

function savedFormat(key) {
  try { return localStorage.getItem(key) === "mcem" ? "mcem" : "standard"; }
  catch { return "standard"; }
}

export default function DealsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const formatKey = `deals-format:${user?.company_id ?? ""}:${user?.id ?? "guest"}`;
  const [formatChoice, setFormatChoice] = useState(null);
  const format = formatChoice?.key === formatKey ? formatChoice.value : savedFormat(formatKey);
  const isMcem = format === "mcem";
  const changeFormat = value => {
    setFormatChoice({ key: formatKey, value });
    try { localStorage.setItem(formatKey, value); } catch { /* Remember for this visit. */ }
  };
  const [scope, setScope] = useState("all");
  // Board or list: remembered per browser (a convenience, so storage
  // failures in private mode just fall back to the board).
  const focusStage = new URLSearchParams(window.location.search).get("stage");
  const [view, setView] = useState(() => {
    if (focusStage) return "board"; // a stage link wants the board, just this once
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
  const params = { status: "all", ...(scope === "mine" && { mine: true }) };
  const { data: allDeals = [], isLoading, isError, refetch } = useDeals(params);
  const [priority, setPriority] = useState("any");
  const [activeOnly, setActiveOnly] = useState(false);
  const progress = useQuery({ queryKey: ["mcem-report"], queryFn: () => apiClient.get("/mcem/report").then(r => r.data) });
  const progressById = new Map((progress.data?.opportunities ?? []).map(row => [row.id, row]));
  const phases = new Map((progress.data?.opportunities ?? []).map(row => [row.id, row.phase]));
  const phaseOf = deal => !isMcem ? deal.stage : deal.stage === "lost" ? "lost" : deal.mcem_enabled ? phases.get(deal.id) : "untracked";
  const deals = allDeals.filter((d) => (!activeOnly || isOpen(d)) && ((isMcem && d.mcem_enabled) || view === "list" || isOpen(d) || recentlyClosed(d)) && (priority === "any" || (d.priority ?? "medium") === priority));
  const openDeals = deals.filter(isOpen);
  const customers = useCustomerMap();
  const team = useTeamMap();

  // ?new=1 (from the command palette) opens the new-deal form straight away.
  const [searchParams, setSearchParams] = useSearchParams();
  const [creating, setCreating] = useState(() => (searchParams.get("new") ? "lead" : null));
  const [focused, setFocused] = useState(focusStage);
  useEffect(() => {
    if (!focused || isLoading) return undefined;
    document.getElementById(`stage-${focused}`)?.scrollIntoView({ block: "nearest", inline: "center" });
    const timer = setTimeout(() => setFocused(null), 2000);
    return () => clearTimeout(timer);
  }, [focused, isLoading]);

  // The toolbar's two disclosures: the filters panel and the "how it works" note.
  const [showFilters, setShowFilters] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const filtersOn = (priority !== "any" ? 1 : 0) + (activeOnly ? 1 : 0);

  // Straight from a card: plan the next step, or move the deal along.
  const [planFor, setPlanFor] = useState(null);
  const [losing, setLosing] = useState(null);
  const [lostReason, setLostReason] = useState("");
  const queryClient = useQueryClient();
  const move = useMutation({
    mutationFn: ({ deal, body }) => apiClient.patch(`/deals/${deal.id}`, body),
    onSuccess: (_r, { deal, body }) => {
      for (const key of [["deals"], ["deal", deal.id], ["mcem-report"], ["dashboard"], ["customers"], ["customer", deal.customer_id], ["pipeline-accounts"], ["reports"]]) queryClient.invalidateQueries({ queryKey: key });
      setLosing(null);
      if (body.stage === "won") toast.success(t("deals.wonToast"));
      else if (body.stage === "lost") toast(t("deals.lostToast"));
      else toast.success(t("deal.movedTo", { stage: t(`stage.${body.stage}`) }));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const moveDeal = (deal, stage) => {
    if (stage === "lost") {
      setLostReason("");
      setLosing(deal);
    } else {
      move.mutate({ deal, body: { stage } });
    }
  };

  const openTotal = sum(openDeals);
  const columns = isMcem ? [
    ...MCEM_PHASES.map(([label, description], index) => ({ value: label, label, description, index })),
    ...(deals.some(d => !d.mcem_enabled && d.stage !== "lost") ? [{ value: "untracked", label: "Not set up yet", description: "Turn on the advanced pipeline and record evidence on existing opportunities.", index: 0 }] : []),
    { value: "lost", label: t("stage.lost"), closed: true, description: "Closed opportunities with their recorded loss reasons." },
  ] : [
    ...STAGES.map((stage, index) => ({ ...stage, index })),
    { value: "won", label: t("stage.won"), closed: true },
    { value: "lost", label: t("stage.lost"), closed: true },
  ];
  const progressLoading = isMcem && progress.isLoading;

  return (
    <>
      <PageHeader
        title={t("nav.deals")}
        subtitle={isLoading ? undefined : t("deals.subtitle", { count: openDeals.length, amount: formatMoney(openTotal) })}
        actions={
          <>
            {/* Which pipeline this page shows; changes the whole board, so it stays in view. */}
            <FilterChips
              bare
              label={t("deals.format")}
              tone="brand"
              options={[
                { value: "standard", label: t("deals.formatStandard") },
                { value: "mcem", label: t("deals.formatAdvanced") },
              ]}
              value={format}
              onChange={changeFormat}
            />
            <ImportExportButtons entity="deals" />
            {canWrite && (
              <Button onClick={() => setCreating("lead")}>
                <PlusIcon className="h-4 w-4" /> {t("dashboard.newDeal")}
              </Button>
            )}
          </>
        }
      />
      {/* One row: whose deals, filters, how it works, board or list. The
          deals themselves start right below, even on a phone. */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <FilterChips
          bare
          label={t("deals.whose")}
          options={[
            { value: "all", label: t("deals.everyones") },
            { value: "mine", label: t("deals.mine") },
          ]}
          value={scope}
          onChange={setScope}
        />
        <button
          type="button"
          aria-expanded={showFilters}
          aria-controls="deal-filters"
          onClick={() => setShowFilters((v) => !v)}
          className={`pressable inline-flex h-10 items-center gap-1.5 rounded-lg border px-3 text-[13px] font-medium ${
            showFilters || filtersOn ? "border-blue-200 bg-blue-50 text-blue-800" : "border-zinc-200/80 bg-white text-zinc-700 hover:bg-zinc-50"
          }`}
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.6} className="h-4 w-4" aria-hidden="true">
            <path d="M2.5 4h11M4.5 8h7M6.5 12h3" strokeLinecap="round" />
          </svg>
          {t("deals.filters")}
          {filtersOn > 0 && <span className="rounded-full bg-blue-600 px-1.5 text-[11px] font-semibold leading-5 text-white tabular-nums">{filtersOn}</span>}
        </button>
        <button
          type="button"
          aria-expanded={showHelp}
          aria-controls="deal-help"
          onClick={() => setShowHelp((v) => !v)}
          className="pressable inline-flex h-10 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} className="h-4 w-4" aria-hidden="true">
            <circle cx="8" cy="8" r="6.25" />
            <path d="M8 7.25v3.5M8 5.2v.05" strokeLinecap="round" />
          </svg>
          {t("deals.howItWorks")}
        </button>
        <div className="ml-auto">
          <FilterChips
            bare
            label={t("deals.layout")}
            options={[
              { value: "board", label: t("dashboard.board") },
              { value: "list", label: t("deals.list") },
            ]}
            value={view}
            onChange={changeView}
          />
        </div>
      </div>

      {showFilters && (
        <div id="deal-filters" className="mb-4 grid gap-4 rounded-xl border border-zinc-200/80 bg-white p-4 sm:grid-cols-[auto_1fr] sm:items-start sm:gap-8">
          <div>
            <p className="mb-1.5 text-xs font-medium text-zinc-600">{t("priority.label")}</p>
            <FilterChips
              bare
              label={t("priority.label")}
              options={[
                { value: "any", label: t("priority.any") },
                { value: "high", label: t("priority.high") },
                { value: "medium", label: t("priority.medium") },
                { value: "low", label: t("priority.low") },
              ]}
              value={priority}
              onChange={setPriority}
            />
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-zinc-600">{t("deals.show")}</p>
            <label className="flex min-h-10 cursor-pointer items-center gap-2.5 text-sm text-zinc-800">
              <input type="checkbox" className="h-[18px] w-[18px] rounded border-zinc-300 accent-blue-600" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} />
              {t("deals.openOnly")}
            </label>
          </div>
          {filtersOn > 0 && (
            <button
              type="button"
              className="justify-self-start text-sm font-medium text-blue-700 hover:text-blue-900 sm:col-span-2"
              onClick={() => {
                setPriority("any");
                setActiveOnly(false);
              }}
            >
              {t("deals.clearFilters")}
            </button>
          )}
        </div>
      )}

      {showHelp && (
        <p id="deal-help" className="mb-4 max-w-3xl rounded-xl bg-blue-50/70 px-4 py-3 text-sm leading-relaxed text-zinc-700">
          {isMcem
            ? "The advanced pipeline follows customer progress. Confirm evidence and complete the next checkpoint inside an opportunity to advance. Won opportunities continue through delivery and value reviews; only open sales count toward the forecast."
            : t("deals.helpStandard")}
        </p>
      )}
      {isMcem && <McemReport />}
      {isError || (isMcem && progress.isError) ? (
        <ErrorState onRetry={() => { refetch(); progress.refetch(); }} />
      ) : view === "list" ? (
        <DealTable deals={[...openDeals.sort(byUrgency), ...deals.filter((d) => !isOpen(d)).sort(byClosed)]} customers={customers} team={team} loading={isLoading || progressLoading} phases={phases} isMcem={isMcem} />
      ) : (
        // Customer phases remain visible after Won, including older active accounts.
        <div className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-4 [scrollbar-width:thin] md:mx-0 md:px-0">
          {columns.map((stage) => {
            const column = deals.filter((d) => phaseOf(d) === stage.value).sort(stage.closed ? byClosed : byUrgency);
            const tint = stage.value === "won" ? "bg-emerald-50" : stage.value === "lost" ? "bg-red-50/60" : "bg-zinc-100/70";
            return (
              <section
                key={stage.value}
                id={`stage-${stage.value}`}

                className={`flex w-[85%] shrink-0 snap-start flex-col rounded-xl p-2 transition-[background-color,box-shadow] duration-300 md:w-64 md:min-w-64 ${tint} ${
                  focused === stage.value ? "ring-2 ring-blue-500" : ""
                }`}
              >
                {/* Open stages: slices of one spectrum, read as progress.
                    Won is green and Lost red, so outcomes read at a glance. */}
                {stage.closed ? (
                  <span className={`mx-2 mt-1 block h-[3px] rounded-full ${stage.value === "won" ? "bg-emerald-500" : "bg-red-400"}`} aria-hidden="true" />
                ) : (
                  <span
                    className="spectrum-slice mx-2 mt-1 block h-[3px] rounded-full"
                    style={{ "--slices": isMcem ? MCEM_PHASES.length : STAGES.length, "--slice": stage.index }}
                    aria-hidden="true"
                  />
                )}
                <header className="flex items-start justify-between gap-2 px-2 pb-2.5 pt-2">
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold text-zinc-900">
                      {stage.label} <span className="font-normal text-zinc-600 tabular-nums">{column.length}</span>
                    </h2>
                    <p className="text-xs tabular-nums text-zinc-600" title={formatMoney(sum(column))}>
                      {formatMoneyFit(sum(column))}
                    </p>
                  </div>
                  {canWrite && stage.index === 0 && stage.value !== "untracked" && (
                    <Tooltip label={t("deals.newInStage", { stage: stage.label })} side="top-end">
                      <button
                        type="button"
                        onClick={() => setCreating("lead")}
                        aria-label={t("deals.newInStage", { stage: stage.label })}
                        className="pressable -mr-1 -mt-1 flex h-9 w-9 items-center justify-center rounded-lg text-zinc-600 hover:bg-white hover:text-zinc-900"
                      >
                        <PlusIcon className="h-4 w-4" />
                      </button>
                    </Tooltip>
                  )}
                </header>
                {stage.description && <p className="min-h-14 px-2 pb-3 text-xs leading-relaxed text-zinc-600">{stage.description}</p>}
                <div className="flex min-h-[6rem] flex-1 flex-col gap-2">
                  {isLoading || progressLoading
                    ? [0, 1].map((i) => <div key={i} className="h-24 animate-pulse rounded-lg bg-white/70" />)
                    : column.map((deal) => (
                        <DealCard
                          key={deal.id}
                          deal={deal}
                          customer={customers.get(deal.customer_id)}
                          owner={team.get(deal.owner_id)}
                          progress={progressById.get(deal.id)}
                          canWrite={canWrite}
                          onMove={moveDeal}
                          onPlan={setPlanFor}
                        />
                      ))}
                  {!isLoading && !progressLoading && column.length === 0 && (
                    <p className="rounded-lg border border-dashed border-zinc-300 px-3 py-6 text-center text-xs text-zinc-400">
                      {stage.closed ? t(`deals.none.${stage.value}`) : t("deals.noDeals")}
                    </p>
                  )}
                </div>
              </section>
            );
          })}
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
      <ComposerSheet open={Boolean(planFor)} onClose={() => setPlanFor(null)} mode="activity" dealId={planFor} />
      <Sheet
        open={Boolean(losing)}
        onClose={() => setLosing(null)}
        title={t("deals.markLostTitle")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setLosing(null)}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" disabled={move.isPending} onClick={() => move.mutate({ deal: losing, body: { stage: "lost", lost_reason: lostReason.trim() || null } })}>
              {t("deals.markLost")}
            </Button>
          </>
        }
      >
        <p className="mb-4 text-sm text-zinc-600">{losing?.title}</p>
        <Field label={t("deals.lostReason")} hint={t("deals.lostReasonHint")}>
          <input className="input" value={lostReason} onChange={(e) => setLostReason(e.target.value)} placeholder={t("deals.lostReasonPlaceholder")} maxLength={255} />
        </Field>
      </Sheet>
    </>
  );
}

// Won: the whole card green. Lost: muted, with a red edge. Both unmistakable.
const OUTCOME_CARD = {
  won: "border-2 border-emerald-500 bg-emerald-50 ring-1 ring-inset ring-emerald-200",
  lost: "border border-red-200 bg-zinc-50",
};

const MOVE_TARGETS = [...STAGES.map((s) => s.value), "won", "lost"];

/** "Move" on a card: every other stage, then Won and Lost. A small menu
 *  anchored to the button; Escape or a click outside closes it. */
function MoveMenu({ deal, onMove }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState(null);
  const box = useRef(null);
  const menu = useRef(null);
  // Fixed to the screen, so the board's sideways scroller can't clip it;
  // below the button, or above when there's no room.
  const toggle = () => {
    if (open) return setOpen(false);
    const r = box.current.getBoundingClientRect();
    const height = (MOVE_TARGETS.length + 1) * 38;
    const below = window.innerHeight - r.bottom > height + 12;
    setPlace({ right: Math.max(8, window.innerWidth - r.right), ...(below ? { top: r.bottom + 4 } : { bottom: window.innerHeight - r.top + 4 }) });
    setOpen(true);
  };
  useEffect(() => {
    if (!open) return undefined;
    const outside = (e) => !box.current?.contains(e.target) && !menu.current?.contains(e.target) && setOpen(false);
    const away = () => setOpen(false);
    const key = (e) => {
      if (e.key === "Escape") {
        e.preventDefault(); // closes the menu, not a sheet behind it
        setOpen(false);
        box.current?.querySelector("button")?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", key);
    window.addEventListener("resize", away);
    document.addEventListener("scroll", away, true);
    menu.current?.querySelector('[role="menuitem"]')?.focus();
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", key);
      window.removeEventListener("resize", away);
      document.removeEventListener("scroll", away, true);
    };
  }, [open]);
  const targets = MOVE_TARGETS.filter((s) => s !== deal.stage);
  const step = (e, dir) => {
    const items = [...menu.current.querySelectorAll('[role="menuitem"]')];
    const i = items.indexOf(document.activeElement);
    items[(i + dir + items.length) % items.length]?.focus();
    e.preventDefault();
  };
  return (
    <div ref={box} className="relative z-10">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("deals.moveDeal", { title: deal.title })}
        onClick={toggle}
        className="pressable inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs font-medium text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 [@media(pointer:coarse)]:h-10"
      >
        {t("deals.move")}
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-3.5 w-3.5" aria-hidden="true">
          <path d="m4.5 6.5 3.5 3.5 3.5-3.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open &&
        place &&
        createPortal(
        <ul
          ref={menu}
          role="menu"
          style={place}
          aria-label={t("deals.moveTo")}
          onKeyDown={(e) => (e.key === "ArrowDown" ? step(e, 1) : e.key === "ArrowUp" ? step(e, -1) : null)}
          className="fixed z-50 w-48 rounded-xl bg-white py-1 text-sm shadow-pop ring-1 ring-zinc-200"
        >
          <li role="presentation" className="px-3 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
            {t("deals.moveTo")}
          </li>
          {targets.map((stage) => (
            <li role="presentation" key={stage} className={stage === "won" ? "mt-1 border-t border-zinc-100 pt-1" : ""}>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onMove(deal, stage);
                }}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-zinc-50 focus:bg-zinc-50 focus:outline-none [@media(pointer:coarse)]:py-2.5 ${
                  stage === "won" ? "font-medium text-emerald-700" : stage === "lost" ? "text-red-700" : "text-zinc-800"
                }`}
              >
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${stage === "won" ? "bg-emerald-500" : stage === "lost" ? "bg-red-400" : "spectrum-slice"}`}
                  style={stage === "won" || stage === "lost" ? undefined : { "--slices": STAGES.length, "--slice": STAGES.findIndex((s) => s.value === stage) }}
                  aria-hidden="true"
                />
                {t(`stage.${stage}`)}
              </button>
            </li>
          ))}
        </ul>,
          document.body,
        )}
    </div>
  );
}

function OutcomeBadge({ deal }) {
  const { t } = useTranslation();
  const won = deal.stage === "won";
  return (
    <span className={`mb-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${won ? "bg-emerald-600 text-white" : "bg-red-100 text-red-700"}`}>
      {won ? "✓" : "✕"} {t(`stage.${deal.stage}`)}
      {deal.closed_at && <span className="font-normal opacity-80">· {formatShortDate(deal.closed_at.slice(0, 10))}</span>}
    </span>
  );
}

function DealCard({ deal, customer, owner, progress, canWrite, onMove, onPlan }) {
  const { t } = useTranslation();
  // MCEM opportunities move only through their evidence checkpoints.
  const quickMove = canWrite && !deal.mcem_enabled;
  return (
    // The title's link covers the whole card; the buttons sit above it.
    <div
      className={`relative rounded-lg p-3 shadow-xs transition-shadow duration-150 focus-within:ring-2 focus-within:ring-blue-500 hover:shadow-card ${OUTCOME_CARD[deal.stage] ?? "border border-zinc-200/80 bg-white"}`}
    >
      {deal.stage === "won" || deal.stage === "lost" ? <OutcomeBadge deal={deal} /> : null}
      <p className={`flex items-start justify-between gap-2 text-sm font-medium leading-snug ${deal.stage === "won" ? "text-emerald-950" : deal.stage === "lost" ? "text-zinc-600" : "text-zinc-900"}`}>
        <Link to={`/deals/${deal.id}`} draggable={false} className="min-w-0 after:absolute after:inset-0 after:rounded-lg focus:outline-none">
          {deal.title}
        </Link>
        {isOpen(deal) && <PriorityBadge priority={deal.priority} quiet />}
      </p>
      <p className="mt-0.5 break-words text-xs text-zinc-500">{customer?.name ?? "…"}</p>
      {!deal.mcem_enabled && deal.stage !== "lost" && <JourneyBar milestones={deal.milestones} className="mt-2.5" />}
      <div className="mt-2.5 flex items-center justify-between gap-2">
        <span className={`text-sm font-semibold ${deal.stage === "won" ? "text-emerald-800" : deal.stage === "lost" ? "text-zinc-500 line-through decoration-red-300" : "text-zinc-900"}`}>
          {formatMoney(deal.value)}
        </span>
        {owner && <Avatar name={owner.full_name} size="sm" />}
      </div>
      {progress && deal.stage !== "lost" && <div className="mt-2 space-y-1 text-xs text-zinc-600">
        {progress.overdue_milestones > 0 && <p className="text-red-700">{progress.overdue_milestones} overdue milestones</p>}
        {progress.needs_review > 0 && <p className="text-amber-800">{progress.needs_review} confirmations need review</p>}
        {deal.stage === "won" && progress.next_review_date && <p>Next review: {formatShortDate(progress.next_review_date)}</p>}
        {deal.stage === "won" && progress.renewal_date && <p>Renewal: {formatShortDate(progress.renewal_date)}</p>}
      </div>}
      {deal.stage === "lost" && deal.lost_reason && <p className="mt-2 border-t border-red-100 pt-2 text-xs text-red-800">{deal.lost_reason}</p>}
      {(isOpen(deal) || quickMove) && (
        <div className="mt-2 flex min-h-8 items-center justify-between gap-2 border-t border-zinc-100 pt-2">
          {isOpen(deal) && deal.next_activity ? (
            <NextActivityBadge activity={deal.next_activity} />
          ) : isOpen(deal) && canWrite ? (
            // Nothing planned: one tap to plan it, instead of a warning on every card.
            <button
              type="button"
              onClick={() => onPlan(deal.id)}
              className="pressable relative z-10 -ml-1.5 inline-flex h-8 items-center gap-1 rounded-md px-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 [@media(pointer:coarse)]:h-10"
            >
              <PlusIcon className="h-3.5 w-3.5" />
              {t("deals.planNext")}
            </button>
          ) : (
            <span />
          )}
          {quickMove && <MoveMenu deal={deal} onMove={onMove} />}
        </div>
      )}
    </div>
  );
}

/** The same deals as a table: the view for scanning, sorting by eye and
    comparing values, where the board is for moving things along. */
function DealTable({ deals, customers, team, loading, phases, isMcem }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [editing, setEditing] = useState(null);
  if (loading) return <div className="card h-48 animate-pulse" />;
  return (
    <div className="card overflow-hidden">
      <DealFormSheet open={Boolean(editing)} onClose={() => setEditing(null)} deal={editing} />
      {/* Long column names in some languages: scroll sideways inside the card, never cut off. */}
      <div className="relative hidden overflow-x-auto md:block">
      <table className="w-full">
        <thead className="table-head">
          <tr>
            <th>{t("deals.col.deal")}</th>
            <th>{isMcem ? "Phase / outcome" : t("deals.col.stage")}</th>
            <th>{t("priority.label")}</th>
            <th className="w-28">{t("journey.column")}</th>
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
            const stageIndex = isMcem ? MCEM_PHASES.findIndex(([label]) => label === phases.get(deal.id)) : STAGES.findIndex(stage => stage.value === deal.stage);
            const owner = team.get(deal.owner_id);
            return (
              <tr
                key={deal.id}
                className={`table-row ${deal.stage === "won" ? "!bg-emerald-50 hover:!bg-emerald-100/70" : deal.stage === "lost" ? "!bg-zinc-50 text-zinc-500" : ""}`}
                onClick={() => navigate(`/deals/${deal.id}`)}
              >
                <td>
                  <Link to={`/deals/${deal.id}`} onClick={(e) => e.stopPropagation()} className="font-medium text-zinc-900 hover:underline">
                    {deal.title}
                  </Link>
                  <p className="text-xs text-zinc-500">{customers.get(deal.customer_id)?.name ?? "…"}</p>
                </td>
                <td>
                  {deal.stage === "won" || deal.stage === "lost" ? (
                    <span className={`inline-flex items-center gap-1.5 font-medium ${deal.stage === "won" ? "text-emerald-700" : "text-red-700"}`}>
                      <span className={`h-2 w-2 rounded-full ${deal.stage === "won" ? "bg-emerald-500" : "bg-red-400"}`} aria-hidden="true" />
                      {t(`stage.${deal.stage}`)}{isMcem && deal.stage === "won" && phases.get(deal.id) ? ` / ${phases.get(deal.id)}` : ""}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-2 text-zinc-700">
                      {/* The stage's spectrum slice, as on the board's column bar. */}
                      <span
                        className="spectrum-slice h-2 w-2 rounded-full"
                        style={{ "--slices": isMcem ? MCEM_PHASES.length : STAGES.length, "--slice": Math.max(0, stageIndex) }}
                        aria-hidden="true"
                      />
                      {isMcem ? phases.get(deal.id) ?? "Not set up yet" : t(`stage.${deal.stage}`)}
                    </span>
                  )}
                </td>
                <td>
                  <PriorityBadge priority={deal.priority} />
                </td>
                <td>
                  <span className="flex items-center gap-2">
                    {deal.mcem_enabled ? <Link className="text-xs text-indigo-700 underline" to={`/deals/${deal.id}`}>View milestones</Link> : <><JourneyBar milestones={deal.milestones} className="w-16" /><span className="text-xs tabular-nums text-slate-500">{journeyPercent(deal.milestones)}%</span></>}
                  </span>
                </td>
                <td className="whitespace-nowrap text-right font-medium tabular-nums text-zinc-900">{formatMoney(deal.value)}</td>
                <td className="text-zinc-600">{industryLabel(deal.industry) || "—"}</td>
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
      </div>
      <ul className="divide-y divide-zinc-100 md:hidden">
        {deals.map((deal) => (
          <li key={deal.id}>
            <Link to={`/deals/${deal.id}`} className="flex items-center justify-between gap-3 px-4 py-3.5 active:bg-zinc-50">
              <div className="min-w-0">
                <p className="flex items-start gap-2 font-medium leading-snug text-zinc-900">
                  <span className="min-w-0 break-words">{deal.title}</span>
                  {isOpen(deal) && <PriorityBadge priority={deal.priority} quiet />}
                </p>
                <p className="mt-0.5 break-words text-[13px] text-zinc-500">
                  {customers.get(deal.customer_id)?.name ?? "…"} · {!isMcem || deal.stage === "lost" ? t(`stage.${deal.stage}`) : phases.get(deal.id) ?? "Not set up yet"}
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
