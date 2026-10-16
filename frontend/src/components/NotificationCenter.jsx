// The person's own notifications: reminders that activities are due,
// tasks assigned to them, and updates on tasks they handed out
// (backend app/services/notify.py). Listed behind the bell; a new one
// pops up with a soft chime while YGT is open, and arrives as a push
// message on phones and computers that allowed it (utils/push.js).
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { formatShortDate } from "../utils/format";
import { enablePush, pushState, refreshPush } from "../utils/push";

const POLL_MS = 15 * 1000; // a reminder lands close to "a minute before"

export function useMyNotifications(enabled = true) {
  return useQuery({
    queryKey: ["notifications"],
    queryFn: () => apiClient.get("/notifications").then((r) => r.data),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    enabled,
  });
}

/** A notification in the person's language (from its kind and params). */
export function notificationText(n, t) {
  const p = n.params ?? {};
  switch (n.kind) {
    case "activity_due":
      return { title: p.time ? t("notify.dueAt", { time: p.time, subject: p.subject }) : t("notify.dueToday", { subject: p.subject }), body: null };
    case "task_assigned":
      return { title: t("notify.assigned", { by: p.by, subject: p.subject }), body: p.time ? t("notify.dueOnAt", { date: formatShortDate(p.due), time: p.time }) : p.due ? t("notify.dueOn", { date: formatShortDate(p.due) }) : null };
    case "task_update":
      return { title: p.status ? t("notify.updated", { by: p.by, status: t(`task.status.${p.status}`), subject: p.subject }) : t("notify.noted", { by: p.by, subject: p.subject }), body: p.note };
    case "deal_no_next_step":
      return { title: t("notify.noNextStep", { deal: p.deal }), body: t("notify.noNextStepBody") };
    case "test":
      return { title: t("notify.test"), body: t("notify.testBody") };
    default:
      return { title: n.title, body: n.body };
  }
}

function ago(iso, t) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return t("notify.justNow");
  if (minutes < 60) return t("notify.minutesAgo", { count: minutes });
  if (minutes < 24 * 60) return t("notify.hoursAgo", { count: Math.round(minutes / 60) });
  return formatShortDate(iso.slice(0, 10));
}

/** Two soft notes: "something for you". Quiet, and only for new ones. */
function chime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [880, 1320].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = freq;
      osc.type = "sine";
      const start = ctx.currentTime + i * 0.12;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.08, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.35);
      osc.connect(gain).connect(ctx.destination);
      osc.start(start);
      osc.stop(start + 0.4);
    });
    setTimeout(() => ctx.close(), 1200);
  } catch {
    /* no sound available: the pop-up still shows */
  }
}

/** While YGT is open: a new notification pops up (and chimes). Mounted
 *  once, in the app layout. */
export function NotificationPopper() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data } = useMyNotifications();
  const seen = useRef(null);
  useEffect(() => {
    refreshPush();
  }, []);
  useEffect(() => {
    if (!data) return;
    const items = data.items ?? [];
    if (seen.current === null) {
      // First load: what's already there isn't news.
      seen.current = new Set(items.map((n) => n.id));
      return;
    }
    const fresh = items.filter((n) => !seen.current.has(n.id) && !n.read_at);
    items.forEach((n) => seen.current.add(n.id));
    if (!fresh.length) return;
    chime();
    for (const n of fresh.slice(0, 3)) {
      const text = notificationText(n, t);
      toast(text.title, {
        description: text.body || undefined,
        duration: 8000,
        action: n.link ? { label: t("notify.open"), onClick: () => navigate(n.link) } : undefined,
      });
    }
  }, [data, t, navigate]);
  return null;
}

/** The list behind the bell. */
export function NotificationList({ onNavigate }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data } = useMyNotifications();
  const items = data?.items ?? [];
  const read = useMutation({
    mutationFn: (ids) => apiClient.post("/notifications/read", { ids }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
  if (!items.length) return null;
  return (
    <div className="border-t border-slate-100 pt-1">
      <div className="flex items-center justify-between px-4 pb-1 pt-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{t("notify.recent")}</p>
        {data.unread > 0 && (
          <button type="button" className="text-xs font-medium text-blue-600 hover:text-blue-800" onClick={() => read.mutate(null)}>
            {t("notify.markAllRead")}
          </button>
        )}
      </div>
      <ul className="max-h-80 overflow-y-auto">
        {items.slice(0, 12).map((n) => {
          const text = notificationText(n, t);
          return (
            <li key={n.id}>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  if (!n.read_at) read.mutate([n.id]);
                  onNavigate?.();
                  if (n.link) navigate(n.link);
                }}
                className={`flex w-full items-start gap-2.5 px-4 py-2.5 text-left hover:bg-slate-50 ${n.read_at ? "" : "bg-blue-50/40"}`}
              >
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.read_at ? "bg-transparent" : "bg-blue-500"}`} aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium leading-snug text-slate-800">{text.title}</span>
                  {text.body && <span className="mt-0.5 line-clamp-2 block text-xs text-slate-500">{text.body}</span>}
                  <span className="mt-0.5 block text-[11px] text-slate-400">{ago(n.created_at, t)}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** "Alerts on this phone/computer": on, off, or why not. */
export function PushToggle() {
  const { t } = useTranslation();
  const [state, setState] = useState("checking");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    pushState().then(setState).catch(() => setState("unsupported"));
  }, []);
  if (state === "checking" || state === "on") {
    return state === "on" ? <p className="px-4 pb-3 pt-2 text-xs text-emerald-700">✓ {t("notify.pushOn")}</p> : null;
  }
  if (state === "unsupported" || state === "unavailable" || state === "blocked") {
    return <p className="px-4 pb-3 pt-2 text-xs text-slate-500">{t(`notify.push.${state}`)}</p>;
  }
  return (
    <div className="px-4 pb-3 pt-2">
      <button
        type="button"
        disabled={busy}
        className="btn btn-secondary !h-9 w-full !text-sm"
        onClick={async () => {
          setBusy(true);
          try {
            const next = await enablePush();
            setState(next);
            if (next === "on") {
              await apiClient.post("/notifications/test");
              toast.success(t("notify.pushOn"));
            }
          } catch {
            toast.error(t("notify.push.failed"));
          } finally {
            setBusy(false);
          }
        }}
      >
        {t("notify.turnOn")}
      </button>
      <p className="mt-1.5 text-[11px] leading-snug text-slate-500">{t("notify.turnOnHint")}</p>
    </div>
  );
}

export function NotificationsLink() {
  const { t } = useTranslation();
  return (
    <Link to="/activities" className="block px-4 py-2 text-xs font-medium text-blue-600 hover:text-blue-800">
      {t("notify.goToActivities")}
    </Link>
  );
}
