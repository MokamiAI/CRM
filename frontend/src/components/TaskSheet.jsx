// A task (any activity) with its progress: who it's for and from, a status
// (to do, in progress, blocked, done) and the notes people left on it.
// Reporting back tells whoever assigned it (backend add_update).
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { useTeamMap } from "../hooks/useApi";
import { errorMessage, formatShortDate } from "../utils/format";
import Attachments from "./Attachments";
import Sheet from "./Sheet";
import { Avatar } from "./ui";

export const TASK_STATUSES = ["todo", "in_progress", "blocked", "done"];

export const STATUS_TONE = {
  todo: "bg-zinc-100 text-zinc-700 ring-zinc-200",
  in_progress: "bg-blue-50 text-blue-700 ring-blue-200",
  blocked: "bg-red-50 text-red-700 ring-red-200",
  done: "bg-emerald-50 text-emerald-700 ring-emerald-200",
};

const SELECTED = {
  todo: "bg-zinc-100 text-zinc-900 ring-zinc-400",
  in_progress: "bg-blue-50 text-blue-800 ring-blue-400",
  blocked: "bg-red-50 text-red-800 ring-red-400",
  done: "bg-emerald-50 text-emerald-800 ring-emerald-400",
};

export function StatusChip({ status = "todo", className = "" }) {
  const { t } = useTranslation();
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${STATUS_TONE[status] ?? STATUS_TONE.todo} ${className}`}>
      {t(`task.status.${status}`)}
    </span>
  );
}

export default function TaskSheet({ activity, open, onClose }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const team = useTeamMap();
  const queryClient = useQueryClient();
  const canWrite = user?.role !== "viewer";
  const [status, setStatus] = useState(null);
  const [note, setNote] = useState("");
  const { data: updates = [] } = useQuery({
    queryKey: ["task-updates", activity?.id],
    queryFn: () => apiClient.get(`/activities/${activity.id}/updates`).then((r) => r.data),
    enabled: Boolean(open && activity),
  });
  const current = activity?.status ?? "todo";
  const chosen = status ?? current;
  const needsNote = (chosen === "done" || chosen === "blocked") && chosen !== current;
  const send = useMutation({
    mutationFn: () =>
      apiClient.post(`/activities/${activity.id}/updates`, {
        ...(chosen !== current && { status: chosen }),
        ...(note.trim() && { note: note.trim() }),
      }),
    onSuccess: () => {
      for (const key of ["activities", "task-updates", "deals", "deal", "timeline", "notifications", "mcem", "mcem-report"]) queryClient.invalidateQueries({ queryKey: [key] });
      toast.success(t("task.sent"));
      setStatus(null);
      setNote("");
      onClose();
    },
    onError: (err) => toast.error(errorMessage(err)),
  });
  if (!activity) return null;
  const owner = team.get(activity.owner_id);
  const by = team.get(activity.created_by);
  const unchanged = chosen === current && !note.trim();

  return (
    <Sheet
      open={open}
      onClose={() => {
        setStatus(null);
        setNote("");
        onClose();
      }}
      title={activity.subject}
      footer={
        canWrite && (
          <button type="button" className="btn btn-primary" disabled={unchanged || (needsNote && !note.trim()) || send.isPending} onClick={() => send.mutate()}>
            {send.isPending ? t("common.sending") : t("task.send")}
          </button>
        )
      }
    >
      <div className="space-y-5">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-zinc-500">{t("task.assignedTo")}</dt>
            <dd className="mt-0.5 font-medium text-zinc-900">{owner?.full_name ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-zinc-500">{t("task.assignedBy")}</dt>
            <dd className="mt-0.5 font-medium text-zinc-900">{by?.full_name ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-zinc-500">{t("task.deadline")}</dt>
            <dd className="mt-0.5 font-medium text-zinc-900">
              {formatShortDate(activity.due_date)}
              {activity.due_time && ` · ${activity.due_time.slice(0, 5)}`}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-zinc-500">{t("task.statusLabel")}</dt>
            <dd className="mt-0.5">
              <StatusChip status={current} />
            </dd>
          </div>
        </dl>
        {activity.note && <p className="whitespace-pre-line rounded-lg bg-zinc-50 px-3 py-2 text-sm text-zinc-700">{activity.note}</p>}

        <Attachments activityId={activity.id} canWrite={canWrite} />

        {canWrite && (
          <fieldset>
            <legend className="mb-1.5 block text-sm font-medium text-zinc-700">{t("task.update")}</legend>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {TASK_STATUSES.map((s) => (
                <label
                  key={s}
                  className={`flex min-h-11 cursor-pointer items-center justify-center rounded-lg px-2 text-center text-sm font-medium ring-1 ring-inset transition-colors duration-150 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-indigo-500 ${
                    chosen === s ? SELECTED[s] : "bg-white text-zinc-700 ring-zinc-200 hover:bg-zinc-50"
                  }`}
                >
                  <input type="radio" name="task-status" value={s} checked={chosen === s} onChange={() => setStatus(s)} className="sr-only" />
                  {t(`task.status.${s}`)}
                </label>
              ))}
            </div>
            <label className="mt-3 block text-sm font-medium text-zinc-700" htmlFor="task-note">
              {t(needsNote ? "task.noteRequired" : "task.note")}
            </label>
            <textarea
              id="task-note"
              className="input mt-1.5 min-h-[5rem]"
              rows={3}
              maxLength={2000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t(chosen === "blocked" ? "task.blockedPlaceholder" : chosen === "done" ? "task.donePlaceholder" : "task.notePlaceholder")}
            />
          </fieldset>
        )}

        <section>
          <h3 className="text-sm font-semibold text-zinc-900">{t("task.history")}</h3>
          {updates.length ? (
            <ol className="mt-2 space-y-3">
              {[...updates].reverse().map((u) => {
                const who = team.get(u.author_id);
                return (
                  <li key={u.id} className="flex gap-2.5">
                    <Avatar name={who?.full_name ?? "?"} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                        <span className="font-medium text-zinc-800">{who?.full_name ?? "—"}</span>
                        {u.status && <StatusChip status={u.status} />}
                        <span>{formatShortDate(u.created_at.slice(0, 10))}</span>
                      </p>
                      {u.note && <p className="mt-1 whitespace-pre-line text-sm text-zinc-700">{u.note}</p>}
                    </div>
                  </li>
                );
              })}
            </ol>
          ) : (
            <p className="mt-1 text-sm text-zinc-500">{t("task.noHistory")}</p>
          )}
        </section>
      </div>
    </Sheet>
  );
}
