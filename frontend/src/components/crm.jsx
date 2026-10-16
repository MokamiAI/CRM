import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useTeam, useTeamMap } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import Sheet from "./Sheet";
import { Button, Field } from "./ui";
import i18n from "../i18n";
import { errorMessage, formatDateTime, formatMoney, formatShortDate, todayISO } from "../utils/format";

// ---------- Pipeline vocabulary ----------

// Labels are getters into the translation catalog, so every existing
// `stage.label` / `STAGE_LABELS[x]` reads the current language. (The app
// re-renders on a language switch, so these are re-read then.)
const translated = (values, prefix) =>
  values.map((value) => ({
    value,
    get label() {
      return i18n.t(`${prefix}.${value}`);
    },
  }));

export const STAGES = translated(["lead", "qualified", "proposal", "negotiation"], "stage");
export const STAGE_LABELS = new Proxy({}, { get: (_, stage) => i18n.t(`stage.${String(stage)}`) });

// A deal's importance to the business; high leads each pipeline column.
export const PRIORITIES = ["high", "medium", "low"];
export const PRIORITY_RANK = { high: 0, medium: 1, low: 2 };
const PRIORITY_TONE = {
  high: "bg-red-50 text-red-700 ring-red-200",
  medium: "bg-amber-50 text-amber-800 ring-amber-200",
  low: "bg-zinc-100 text-zinc-600 ring-zinc-200",
};

/** "High", "Medium" or "Low", as a small tag. `quiet`: show nothing for
 *  Low, so a busy board only marks what matters. */
export function PriorityBadge({ priority = "medium", quiet = false, className = "" }) {
  if (quiet && priority === "low") return null;
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${PRIORITY_TONE[priority] ?? PRIORITY_TONE.medium} ${className}`}>
      {priority === "high" && (
        <svg viewBox="0 0 16 16" fill="currentColor" className="h-3 w-3" aria-hidden="true">
          <path d="M3 2a1 1 0 0 1 1 1v.3l7.6-.9a.8.8 0 0 1 .7 1.3L11 5.8l1.3 2.1a.8.8 0 0 1-.7 1.3L4 10.1V14a1 1 0 1 1-2 0V3a1 1 0 0 1 1-1Z" />
        </svg>
      )}
      {i18n.t(`priority.${priority}`)}
    </span>
  );
}

// Same codes as INDUSTRIES in backend app/models/enums.py.
export const INDUSTRY_CODES = [
  "agriculture", "automotive", "construction", "education", "energy", "financial_services", "food_beverage",
  "government", "healthcare", "hospitality", "insurance", "it_software", "legal", "manufacturing",
  "media_marketing", "mining", "non_profit", "professional_services", "real_estate", "retail", "telecoms",
  "transport_logistics", "wholesale", "other",
];
export const industryLabel = (code) => (code ? i18n.t(`industry.${code}`) : "");
/** Industries sorted by their label in the current language, "Other" last. */
export function industryOptions() {
  return INDUSTRY_CODES.filter((c) => c !== "other")
    .map((value) => ({ value, label: industryLabel(value) }))
    .sort((a, b) => a.label.localeCompare(b.label))
    .concat({ value: "other", label: industryLabel("other") });
}

/** Best guess from a customer's own "Industry" custom field (e.g. "Mining"). */
export function industryFromCustomer(customer) {
  const raw = Object.entries(customer?.custom_fields ?? {}).find(([key]) => key.toLowerCase().startsWith("industry"))?.[1];
  if (!raw) return "";
  const text = String(raw).toLowerCase();
  return (
    INDUSTRY_CODES.find((code) => code !== "other" && (text.includes(code.split("_")[0]) || industryLabel(code).toLowerCase() === text)) ?? ""
  );
}

export const ACTIVITY_TYPES = translated(["call", "meeting", "task", "email", "deadline"], "activityType");

const ICON_PATHS = {
  call: "M5 4h3l2 5-2.5 1.5a11 11 0 0 0 6 6L15 14l5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2",
  meeting: "M8 2v4M16 2v4M3 9h18M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z",
  task: "M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
  email: "M4 6h16v12H4zM4 7l8 6 8-6",
  deadline: "M5 21V4M5 4h11l-2 4 2 4H5",
  note: "M4 4h16v12H8l-4 4V4Z",
};

export function ActivityIcon({ type, className = "h-4 w-4" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={ICON_PATHS[type] ?? ICON_PATHS.task} />
    </svg>
  );
}

/** Where an open activity stands relative to today (company calendar day). */
export function dueState(dueDate) {
  const today = todayISO();
  if (dueDate < today) return "overdue";
  if (dueDate === today) return "today";
  return "upcoming";
}

const DUE_STYLES = {
  overdue: "text-red-600",
  today: "text-emerald-600",
  upcoming: "text-zinc-500",
};

export function dueLabel(dueDate, dueTime) {
  const state = dueState(dueDate);
  const time = dueTime ? ` · ${dueTime.slice(0, 5)}` : "";
  if (state === "today") return `${i18n.t("due.today")}${time}`;
  if (state === "overdue") return `${formatShortDate(dueDate)} · ${i18n.t("due.overdue")}`;
  return `${formatShortDate(dueDate)}${time}`;
}

/**
 * Pipedrive's deal-card signal: what's next on this deal. Overdue (red),
 * due today (green), nothing planned (amber, the "deal is going cold"
 * warning), or a future date. Always icon + words, never color alone.
 */
export function NextActivityBadge({ activity }) {
  const { t } = useTranslation();
  if (!activity) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700">
        <svg viewBox="0 0 16 16" fill="currentColor" className="h-3.5 w-3.5" aria-hidden="true">
          <path d="M8 1.5a1 1 0 0 1 .87.5l6 10.5A1 1 0 0 1 14 14H2a1 1 0 0 1-.87-1.5l6-10.5A1 1 0 0 1 8 1.5ZM8 6a.75.75 0 0 0-.75.75v2.5a.75.75 0 0 0 1.5 0v-2.5A.75.75 0 0 0 8 6Zm0 6a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8Z" />
        </svg>
        {t("due.noNextStep")}
      </span>
    );
  }
  const state = dueState(activity.due_date);
  return (
    <span className={`inline-flex min-w-0 items-center gap-1 text-xs font-medium ${DUE_STYLES[state]}`}>
      <ActivityIcon type={activity.type} className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate">{state === "today" ? t("due.today") : state === "overdue" ? t("due.overdueTitle") : formatShortDate(activity.due_date)}</span>
    </span>
  );
}

// ---------- Activity row with a done checkbox ----------

// Completing a row: the check draws in (160ms), holds briefly so it
// registers, then the row collapses out of the list (220ms) before the
// list refetches without it. Every list of activities is filtered by
// done/not-done, so a toggled row always leaves.
const CHECK_BEAT_MS = 320;
const COLLAPSE_MS = 220;

/** Pencil button that opens the activity in the composer to edit it. */
export function EditActivityButton({ activity, className = "" }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  if (user?.role === "viewer") return null;
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={t("edit.activity", { subject: activity.subject })}
        className={`pressable flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 ${className}`}
      >
        <PencilIcon className="h-4 w-4" />
      </button>
      <ComposerSheet open={open} onClose={() => setOpen(false)} mode="activity" activity={activity} />
    </>
  );
}

// ---------- Lead to client ----------

// The six steps from a lead to a client; the server says which are reached.
export const MILESTONES = ["lead", "contacted", "qualified", "quote_sent", "negotiation", "won"];

export function journeyPercent(milestones = []) {
  return Math.round((MILESTONES.filter((m) => milestones.includes(m)).length / MILESTONES.length) * 100);
}

/** Thin progress bar for cards and rows: how far a lead is to a client. */
export function JourneyBar({ milestones, className = "" }) {
  const { t } = useTranslation();
  const pct = journeyPercent(milestones);
  return (
    <span
      className={`block h-1.5 overflow-hidden rounded-full bg-slate-100 ${className}`}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      aria-label={t("journey.aria", { pct })}
    >
      <span className={`block h-full rounded-full ${pct === 100 ? "bg-emerald-500" : "bg-blue-600"}`} style={{ width: `${pct}%` }} />
    </span>
  );
}

/** Deal page: percentage, the six steps ticked from real activity, and
 *  the next one to take. */
export function DealJourney({ milestones }) {
  const { t } = useTranslation();
  const pct = journeyPercent(milestones);
  const next = MILESTONES.find((m) => !milestones.includes(m));
  return (
    <section className="card p-4 sm:p-5" aria-label={t("journey.title")}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-midnight">{t("journey.title")}</h2>
        <span className={`text-sm font-bold tabular-nums ${pct === 100 ? "text-emerald-600" : "text-blue-700"}`}>{t("journey.percent", { pct })}</span>
      </div>
      <JourneyBar milestones={milestones} className="mt-2 !h-2" />
      <ol className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-3 lg:grid-cols-6">
        {MILESTONES.map((m) => {
          const done = milestones.includes(m);
          return (
            <li key={m} className={`flex items-center gap-1.5 ${done ? "text-slate-700" : m === next ? "font-semibold text-blue-700" : "text-slate-400"}`}>
              <span
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full ${done ? "bg-emerald-500 text-white" : m === next ? "ring-2 ring-blue-600" : "ring-1 ring-slate-300"}`}
                aria-hidden="true"
              >
                {done && (
                  <svg viewBox="0 0 16 16" fill="none" className="h-2.5 w-2.5">
                    <path d="M3.5 8.5 6.5 11.5 12.5 4.5" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </span>
              <span>{t(`journey.step.${m}`)}</span>
              <span className="sr-only">{done ? t("journey.done") : t("journey.todo")}</span>
            </li>
          );
        })}
      </ol>
      {next && <p className="mt-3 text-sm text-slate-600">{t(`journey.next.${next}`)}</p>}
    </section>
  );
}

/** The pencil at the end of a table row: opens the edit (a link or a
 *  sheet) without also opening the row. */
export function RowEditButton({ label, to, onClick }) {
  const cls = "pressable inline-flex h-8 w-8 items-center justify-center rounded-full text-zinc-400 hover:bg-blue-50 hover:text-blue-700";
  const stop = (e) => e.stopPropagation();
  return to ? (
    <Link to={to} onClick={stop} aria-label={label} title={label} className={cls}>
      <PencilIcon className="h-4 w-4" />
    </Link>
  ) : (
    <button
      type="button"
      onClick={(e) => {
        stop(e);
        onClick();
      }}
      aria-label={label}
      title={label}
      className={cls}
    >
      <PencilIcon className="h-4 w-4" />
    </button>
  );
}

export function PencilIcon(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M4 20h4L18.5 9.5a2.1 2.1 0 0 0-3-3L5 17v3Z" />
      <path d="m14 8 3 3" />
    </svg>
  );
}

export function ActivityRow({ activity, context, onToggle }) {
  const { t } = useTranslation();
  const [optimisticDone, setOptimisticDone] = useState(null);
  const [leaving, setLeaving] = useState(false);
  const done = optimisticDone ?? activity.done;
  const state = done ? "done" : dueState(activity.due_date);

  function handleToggle() {
    if (optimisticDone !== null) return; // already on its way out
    setOptimisticDone(!activity.done);
    const reset = () => {
      setOptimisticDone(null);
      setLeaving(false);
    };
    setTimeout(() => setLeaving(true), CHECK_BEAT_MS);
    setTimeout(() => onToggle(activity, { onError: reset }), CHECK_BEAT_MS + COLLAPSE_MS);
  }

  return (
    <li className="row-collapse" data-leaving={leaving}>
      <div>
        <div className="flex items-start gap-3 px-4 py-3 sm:px-5">
          <button
            type="button"
            role="checkbox"
            aria-checked={done}
            aria-label={t(done ? "activity.markUndone" : "activity.markDone", { subject: activity.subject })}
            onClick={handleToggle}
            className={`pressable mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors duration-150 ${
              done ? "border-emerald-500 bg-emerald-500 text-white" : "border-zinc-300 bg-white text-transparent hover:border-zinc-400"
            }`}
          >
            <svg viewBox="0 0 16 16" fill="none" className="h-3 w-3" aria-hidden="true">
              <path className="check-path" d="M3.5 8.5 6.5 11.5 12.5 4.5" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <div className="min-w-0 flex-1">
            <p className={`text-sm font-medium transition-colors duration-150 ${done ? "text-zinc-400 line-through" : "text-zinc-900"}`}>{activity.subject}</p>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-zinc-500">
              <span className="inline-flex items-center gap-1">
                <ActivityIcon type={activity.type} className="h-3.5 w-3.5" />
                {ACTIVITY_TYPES.find((t) => t.value === activity.type)?.label}
              </span>
              {!done && <span className={DUE_STYLES[state]}>{dueLabel(activity.due_date, activity.due_time)}</span>}
              {context}
            </p>
            {activity.note && <p className="mt-1 whitespace-pre-line text-sm text-zinc-600">{activity.note}</p>}
          </div>
          {!done && <EditActivityButton activity={activity} className="-mr-1 -mt-1" />}
        </div>
      </div>
    </li>
  );
}

/** Toggles done, then refreshes everything that shows activities. */
export function useToggleActivity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (activity) => apiClient.patch(`/activities/${activity.id}`, { done: !activity.done }).then((r) => r.data),
    onSuccess: (updated) => {
      const refresh = () => {
        for (const key of ["activities", "deals", "deal", "timeline"]) queryClient.invalidateQueries({ queryKey: [key] });
      };
      refresh();
      if (updated.done) {
        // Ticking things off is fast and easy to fat-finger: offer undo
        // rather than asking for confirmation first.
        toast.success(i18n.t("activity.done"), {
          description: updated.subject,
          action: {
            label: i18n.t("common.undo"),
            onClick: () => apiClient.patch(`/activities/${updated.id}`, { done: false }).then(refresh),
          },
        });
      }
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
}

// ---------- Composer: schedule an activity or write a note ----------

/**
 * One sheet for both kinds of record-level input, like the composer at
 * the top of a HubSpot/Pipedrive record: a scheduled activity, or a note.
 */
export function ComposerSheet({ open, onClose, mode, customerId, dealId, initialType = "call", activity }) {
  const { t } = useTranslation();
  const { data: team = [] } = useTeam();
  const queryClient = useQueryClient();
  const [type, setType] = useState("call");
  const [subject, setSubject] = useState("");
  const [dueDate, setDueDate] = useState(todayISO());
  const [dueTime, setDueTime] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [body, setBody] = useState("");
  const [note, setNote] = useState("");
  const editing = Boolean(activity);

  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setType(activity?.type ?? initialType);
      setSubject(activity?.subject ?? "");
      setBody("");
      setNote(activity?.note ?? "");
      setDueDate(activity?.due_date ?? todayISO());
      setDueTime(activity?.due_time?.slice(0, 5) ?? "");
      setOwnerId(activity?.owner_id ?? "");
    }
  }

  const save = useMutation({
    mutationFn: () =>
      mode === "note"
        ? apiClient.post("/notes", { body, customer_id: dealId ? null : customerId, deal_id: dealId ?? null })
        : editing
          ? apiClient.patch(`/activities/${activity.id}`, { type, subject, note: note || null, due_date: dueDate, due_time: dueTime || null, ...(ownerId && { owner_id: ownerId }) })
          : apiClient.post("/activities", {
              type,
              subject,
              note: note || null,
              due_date: dueDate,
              due_time: dueTime || null,
              customer_id: dealId ? null : customerId,
              deal_id: dealId ?? null,
              owner_id: ownerId || null,
            }),
    onSuccess: () => {
      for (const key of ["activities", "timeline", "deals", "deal"]) queryClient.invalidateQueries({ queryKey: [key] });
      toast.success(t(mode === "note" ? "composer.noteAdded" : editing ? "edit.activitySaved" : "composer.scheduled"));
      onClose();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  function handleSubmit(event) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t(mode === "note" ? "composer.noteTitle" : editing ? "edit.activityTitle" : "composer.activityTitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="composer-form" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? t("common.saving") : t(mode === "note" ? "composer.addNote" : editing ? "edit.save" : "composer.schedule")}
          </button>
        </>
      }
    >
      <form id="composer-form" onSubmit={handleSubmit} className="space-y-4">
        {mode === "note" ? (
          <Field label={t("composer.note")}>
            <textarea className="input" rows={5} required value={body} onChange={(e) => setBody(e.target.value)} placeholder={t("composer.notePlaceholder")} />
          </Field>
        ) : (
          <>
            <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={t("composer.type")}>
              {ACTIVITY_TYPES.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={type === option.value}
                  onClick={() => setType(option.value)}
                  className={`pressable inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium ring-1 ring-inset ${
                    type === option.value ? "bg-zinc-900 text-white ring-zinc-900" : "bg-white text-zinc-600 ring-zinc-200 hover:bg-zinc-50"
                  }`}
                >
                  <ActivityIcon type={option.value} className="h-4 w-4" />
                  {option.label}
                </button>
              ))}
            </div>
            <Field label={t("composer.subject")}>
              <input className="input" required value={subject} onChange={(e) => setSubject(e.target.value)} placeholder={t("composer.subjectPlaceholder")} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("composer.due")}>
                <input className="input" type="date" required value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
              </Field>
              <Field label={t("composer.time")}>
                <input className="input" type="time" value={dueTime} onChange={(e) => setDueTime(e.target.value)} />
              </Field>
            </div>
            <Field label={t("edit.details")}>
              <textarea className="input" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
            </Field>
            {team.length > 1 && (
              <Field label={t("composer.assignedTo")}>
                <select className="input" value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
                  <option value="">{t("composer.me")}</option>
                  {team.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.full_name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
          </>
        )}
      </form>
    </Sheet>
  );
}

// ---------- Timeline ----------

const KIND_ICON = {
  note: "note",
  activity: "task",
  deal_created: "deadline",
  deal_closed: "deadline",
  quote: "email",
  invoice: "email",
  payment: "task",
  reminder: "email",
  message: "email",
};

const KIND_TINT = {
  note: "bg-amber-50 text-amber-700 ring-amber-200/70",
  activity: "bg-emerald-50 text-emerald-700 ring-emerald-200/70",
  deal_created: "bg-violet-50 text-violet-700 ring-violet-200/70",
  deal_closed: "bg-violet-50 text-violet-700 ring-violet-200/70",
  quote: "bg-sky-50 text-sky-700 ring-sky-200/70",
  invoice: "bg-sky-50 text-sky-700 ring-sky-200/70",
  payment: "bg-emerald-50 text-emerald-700 ring-emerald-200/70",
  reminder: "bg-zinc-100 text-zinc-600 ring-zinc-200",
  message: "bg-indigo-50 text-indigo-700 ring-indigo-200/70",
};

function linkFor(item) {
  if (item.kind === "invoice" || item.kind === "payment" || item.kind === "reminder") return `/invoices/${item.ref_id}`;
  if (item.kind === "quote") return `/quotes/${item.ref_id}`;
  if (item.kind === "deal_created" || item.kind === "deal_closed") return `/deals/${item.ref_id}`;
  if (item.kind === "message") return `/messages?c=${item.ref_id}`;
  return null;
}

function formatExact(iso) {
  return formatDateTime(iso, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

// "just now" / "12 min ago" / "3 h ago" / "Yesterday" / "4 Oct": recent
// history reads at a glance; the exact time is in the tooltip.
function formatWhen(iso) {
  const then = new Date(iso);
  const minutes = Math.round((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return i18n.t("time.justNow");
  if (minutes < 60) return i18n.t("time.minutesAgo", { count: minutes });
  if (minutes < 60 * 12) return i18n.t("time.hoursAgo", { count: Math.round(minutes / 60) });
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(iso).setHours(0, 0, 0, 0)) / 86_400_000);
  if (days === 0) return formatDateTime(iso, { hour: "2-digit", minute: "2-digit" });
  if (days === 1) return i18n.t("time.yesterday");
  return formatDateTime(iso, { day: "numeric", month: "short", ...(then.getFullYear() !== new Date().getFullYear() && { year: "numeric" }) });
}

const itemKey = (item) => `${item.kind}-${item.ref_id}-${item.at}`;

// The server sends English title/detail plus structured params; the app
// phrases each entry in the user's language from the params, keeping the
// server text only as a fallback for entries without params.
function describe(item) {
  const p = item.params ?? {};
  if (!Object.keys(p).length && item.kind !== "note") return { title: item.title, detail: item.detail };
  const t = i18n.t.bind(i18n);
  switch (item.kind) {
    case "note":
      return { title: t("timeline.note"), detail: item.detail };
    case "activity":
      return { title: t("timeline.activityDone", { type: t(`activityType.${p.type}`), subject: p.subject }), detail: item.detail };
    case "deal_created":
      return { title: t("timeline.dealCreated", { title: p.title }), detail: t("timeline.value", { amount: formatMoney(p.value) }) };
    case "deal_closed":
      return {
        title: t(p.outcome === "won" ? "timeline.dealWon" : "timeline.dealLost", { title: p.title }),
        detail: p.outcome === "lost" ? p.reason || null : t("timeline.value", { amount: formatMoney(p.value) }),
      };
    case "quote":
      return { title: t("timeline.quote", { number: p.number, status: t(`status.${p.status}`) }), detail: t("timeline.total", { amount: formatMoney(p.total) }) };
    case "invoice":
      return { title: t("timeline.invoice", { number: p.number, status: t(`status.${p.status}`) }), detail: t("timeline.total", { amount: formatMoney(p.total) }) };
    case "payment":
      return {
        title: t("timeline.payment", { number: p.number }),
        detail: [
          t("timeline.paidBy", { amount: formatMoney(p.amount), method: t(`paymentMethod.${p.method}`) }),
          p.reference && t("timeline.reference", { reference: p.reference }),
        ]
          .filter(Boolean)
          .join(" · "),
      };
    case "reminder":
      return { title: t("timeline.reminder", { number: p.number }), detail: t(p.manual === "1" ? "timeline.reminderManual" : "timeline.reminderAuto") };
    case "message":
      return { title: t(p.direction === "in" ? "timeline.messageIn" : "timeline.messageOut", { subject: p.subject }), detail: item.detail };
    default:
      return { title: item.title, detail: item.detail };
  }
}

const TIMELINE_PAGE = 15;

export function Timeline({ items: allItems, hideDealLinks = false, loading = false }) {
  const { t } = useTranslation();
  const team = useTeamMap();
  const [shown, setShown] = useState(TIMELINE_PAGE);
  const items = allItems.slice(0, shown);
  // Entries already there when the timeline first loads render still;
  // only ones that arrive while you're looking (the note you just added)
  // fade in.
  const seen = useRef(null);
  useEffect(() => {
    if (!allItems.length) return;
    seen.current ??= new Set();
    for (const item of allItems) seen.current.add(itemKey(item));
  }, [allItems]);
  if (loading) {
    return (
      <div className="space-y-5 px-5 py-5" aria-busy="true" aria-label={t("timeline.loading")}>
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex gap-3">
            <span className="h-8 w-8 shrink-0 animate-pulse rounded-full bg-zinc-100" />
            <div className="flex-1 space-y-2 pt-1">
              <span className="block h-3.5 w-2/3 animate-pulse rounded bg-zinc-100" />
              <span className="block h-3 w-1/3 animate-pulse rounded bg-zinc-100" />
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (!allItems.length) {
    return <p className="px-5 py-8 text-center text-sm text-zinc-500">{t("timeline.empty")}</p>;
  }
  return (
    <ol className="relative px-4 py-4 sm:px-5">
      {/* The rail: one hairline joining the entries into a single story. */}
      <span className="absolute bottom-6 left-[31px] top-6 w-px bg-zinc-200 sm:left-[35px]" aria-hidden="true" />
      {items.map((item) => {
        const href = linkFor(item);
        const showLink = href && !(hideDealLinks && item.kind.startsWith("deal"));
        const actor = item.actor_id ? team.get(item.actor_id)?.full_name : null;
        const { title, detail } = describe(item);
        return (
          <li key={itemKey(item)} className={`relative flex gap-3 pb-5 last:pb-0 ${seen.current && !seen.current.has(itemKey(item)) ? "timeline-enter" : ""}`}>
            <span className={`relative z-[1] flex h-8 w-8 shrink-0 items-center justify-center rounded-full ring-1 ring-inset ${KIND_TINT[item.kind]}`}>
              <ActivityIcon type={KIND_ICON[item.kind]} className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1 pt-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                {showLink ? (
                  <Link to={href} className="text-sm font-medium text-zinc-900 hover:underline">
                    {title}
                  </Link>
                ) : (
                  <p className="text-sm font-medium text-zinc-900">{title}</p>
                )}
                <time dateTime={item.at} title={formatExact(item.at)} className="shrink-0 text-xs text-zinc-400">
                  {formatWhen(item.at)}
                </time>
              </div>
              {detail && (
                <p className={`mt-1 whitespace-pre-line text-sm text-zinc-600 ${item.kind === "note" ? "rounded-lg bg-amber-50/60 px-3 py-2 ring-1 ring-inset ring-amber-100" : ""}`}>
                  {detail}
                </p>
              )}
              {actor && <p className="mt-1 text-xs text-zinc-400">{actor}</p>}
            </div>
          </li>
        );
      })}
      {allItems.length > shown && (
        <li className="relative pl-11 pt-2">
          <button type="button" onClick={() => setShown((n) => n + TIMELINE_PAGE * 2)} className="text-sm font-medium text-zinc-500 hover:text-zinc-900">
            {t("timeline.showMore", { count: Math.min(allItems.length - shown, TIMELINE_PAGE * 2) })}
          </button>
        </li>
      )}
    </ol>
  );
}

// ---------- Record quick actions ----------

const QUICK_ACTIONS = ["note", "email", "call", "task", "meeting"].map((key) => ({ key, icon: key }));

/**
 * HubSpot's row of record actions: one tap to log or start the common
 * touchpoints. Email and Call hand off to the device (mail app, dialler)
 * when there's an address or number; Note, Task and Meeting open the
 * composer preset to that type.
 */
export function QuickActions({ email, phone, onCompose, canWrite = true }) {
  const { t } = useTranslation();
  return (
    <div className="flex gap-2 overflow-x-auto [scrollbar-width:none]">
      {QUICK_ACTIONS.map((action) => {
        const href = action.key === "email" && email ? `mailto:${email}` : action.key === "call" && phone ? `tel:${phone}` : null;
        const content = (
          <>
            <span className="flex h-9 w-9 items-center justify-center rounded-full border border-zinc-200 bg-white text-zinc-600 shadow-xs transition-colors duration-150 group-hover:border-zinc-300 group-hover:text-zinc-900">
              <ActivityIcon type={action.icon} className="h-4 w-4" />
            </span>
            <span className="text-[11px] font-medium text-zinc-500 group-hover:text-zinc-900">{t(`quickAction.${action.key}`)}</span>
          </>
        );
        const className = "pressable group flex w-14 shrink-0 flex-col items-center gap-1 disabled:opacity-40";
        return href ? (
          <a key={action.key} href={href} className={className}>
            {content}
          </a>
        ) : (
          <button
            key={action.key}
            type="button"
            disabled={!canWrite}
            onClick={() => onCompose(action.key === "note" ? { mode: "note" } : { mode: "activity", type: action.key })}
            className={className}
          >
            {content}
          </button>
        );
      })}
    </div>
  );
}
