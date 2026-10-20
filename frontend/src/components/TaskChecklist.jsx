import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { errorMessage } from "../utils/format";

export function refreshTask(queryClient, updated) {
  if (updated?.id) queryClient.setQueryData(["activity", updated.id], updated);
  for (const key of ["activity", "activities", "task-updates", "meeting-calendar", "deals", "deal", "timeline", "notifications", "mcem", "mcem-report"]) {
    queryClient.invalidateQueries({ queryKey: [key] });
  }
}

export default function TaskChecklist({ activity, canWrite }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [pendingTick, setPendingTick] = useState(null);
  const save = useMutation({
    mutationFn: async ({ method, path, body }) => (await apiClient.request({ method, url: `/activities/${activity.id}${path ?? ""}`, data: body })).data,
    onSuccess: (updated, variables) => {
      refreshTask(queryClient, updated);
      if (variables.method === "post") setTitle("");
    },
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => setPendingTick(null),
  });
  const items = (activity.checklist ?? []).map((item) => pendingTick?.id === item.id ? { ...item, done: pendingTick.done } : item);
  const completed = items.filter((item) => item.done).length;
  const percent = items.length ? Math.round(completed * 100 / items.length) : 0;
  return (
    <section className="space-y-3 rounded-xl border border-zinc-200 p-4" aria-label={t("task.checklist", "Subtasks")}>
      <label className="flex items-center gap-2 text-sm font-semibold text-zinc-900">
        <input type="checkbox" className="h-4 w-4 rounded" checked={activity.checklist_enabled} disabled={!canWrite || save.isPending}
          onChange={(e) => save.mutate({ method: "patch", body: { checklist_enabled: e.target.checked } })} />
        {t("task.useChecklist", "Use a checklist of subtasks")}
      </label>
      {activity.checklist_enabled && (
        <>
          <div>
            <p className="mb-1.5 flex justify-between text-xs font-medium text-zinc-600">
              <span>{t("task.checklistCount", { defaultValue: "{{completed}} of {{total}} complete", completed, total: items.length })}</span>
              <span>{percent}%</span>
            </p>
            <div role="progressbar" aria-label={t("task.progress", "Task completion")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} className="h-2 overflow-hidden rounded-full bg-zinc-100">
              <div className="h-full rounded-full bg-emerald-600" style={{ width: `${percent}%` }} />
            </div>
          </div>
          <p className="text-xs leading-relaxed text-zinc-500">{t("task.checklistHelp", "Ticking items starts the task; completing every item marks it Done. Untick to reopen. Partial progress keeps Blocked unchanged.")}</p>
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.id} className="flex items-center gap-2">
                <label className="flex min-h-11 min-w-0 flex-1 items-center gap-2 text-sm">
                  <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 rounded" checked={item.done} disabled={!canWrite || save.isPending}
                    onChange={(e) => { setPendingTick({ id: item.id, done: e.target.checked }); save.mutate({ method: "patch", path: `/checklist/${item.id}`, body: { done: e.target.checked } }); }} />
                  <span className={`break-words ${item.done ? "text-zinc-500 line-through" : "text-zinc-800"}`}>{item.title}</span>
                </label>
                {canWrite && <button type="button" className="min-h-11 shrink-0 px-1 text-xs text-zinc-500 hover:text-red-600" disabled={save.isPending}
                  aria-label={t("task.removeSubtask", { defaultValue: "Remove {{title}}", title: item.title })}
                  onClick={() => save.mutate({ method: "delete", path: `/checklist/${item.id}` })}>{t("common.remove", "Remove")}</button>}
              </li>
            ))}
          </ul>
          {canWrite && <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (title.trim()) save.mutate({ method: "post", path: "/checklist", body: { title: title.trim() } }); }}>
            <input className="input min-w-0 flex-1" aria-label={t("task.newSubtask", "Add a subtask")} placeholder={t("task.newSubtask", "Add a subtask")} maxLength={255} value={title} onChange={(e) => setTitle(e.target.value)} />
            <button className="btn btn-secondary" disabled={!title.trim() || save.isPending || items.length >= 100}>{t("common.add", "Add")}</button>
          </form>}
        </>
      )}
    </section>
  );
}
