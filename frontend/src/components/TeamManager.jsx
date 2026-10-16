import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useBilling, usePlans } from "../hooks/useApi";
import { errorMessage, formatMoneyWhole } from "../utils/format";
import { Avatar, Button, StatusBadge } from "./ui";

const ROLES = ["admin", "manager", "staff", "viewer"];
const BLANK = { full_name: "", email: "", role: "staff", password: "" };

/** Seats: one per person. How many are used, and what to do when they're
 *  all taken (add seats on Grow/Scale; move up from Hustle's three). */
function SeatsPanel({ billing }) {
  const { t } = useTranslation();
  const { data: plans } = usePlans();
  if (!billing || billing.limits.users == null) return null;
  const used = billing.usage.users;
  const limit = billing.limits.users;
  const free = Math.max(0, limit - used);
  const full = free === 0;
  const plan = plans?.find((p) => p.key === billing.plan);
  const trial = billing.state === "trialing";
  const pct = Math.min(100, (used / Math.max(limit, 1)) * 100);
  const price = plan?.per_user
    ? t("team.seats.price", {
        full: formatMoneyWhole(plan.monthly_cents / 100),
        team: formatMoneyWhole((plan.team_monthly_cents ?? plan.monthly_cents) / 100),
        count: plan.team_seats ?? 3,
      })
    : null;
  let message;
  let action = null;
  if (trial) {
    message = t("team.seats.trial", { limit });
  } else if (!plan?.per_user) {
    message = full ? t("team.seats.hustleFull", { limit }) : t("team.seats.hustle", { limit, free });
    if (full) action = { to: "/settings?tab=billing&plan=grow&seats=" + (used + 1), label: t("team.seats.moveToGrow") };
  } else if (used > limit) {
    // More people than seats (e.g. after moving to fewer seats).
    message = t("team.seats.over", { used, limit, count: used - limit });
    action = { to: `/settings?tab=billing&plan=${billing.plan}&seats=${used + 1}`, label: t("team.seats.addSeats") };
  } else if (full) {
    message = t("team.seats.full", { count: limit });
    action = { to: `/settings?tab=billing&plan=${billing.plan}&seats=${used + 1}`, label: t("team.seats.addSeats") };
  } else {
    message = t("team.seats.room", { count: free });
  }
  const tone = full && !trial ? "bg-amber-50 ring-amber-200/80" : "bg-zinc-50 ring-zinc-200/70";
  return (
    <div className={`rounded-xl p-4 ring-1 ring-inset ${tone}`} role="status">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-zinc-900">{t("team.seats.title")}</p>
        <p className={`text-sm font-semibold tabular-nums ${full && !trial ? "text-amber-800" : "text-zinc-700"}`}>
          {t("team.seats.used", { used, limit })}
        </p>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-white ring-1 ring-inset ring-zinc-200" aria-hidden="true">
        <div className={`h-full rounded-full ${full ? "bg-amber-500" : "bg-indigo-500"}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-sm text-zinc-700">{message}</p>
      {price && !trial && <p className="mt-1 text-xs text-zinc-500">{price}</p>}
      {action && (
        <Link to={action.to} className="btn btn-primary mt-3 !h-9 !text-sm">
          {action.label}
        </Link>
      )}
    </div>
  );
}

/** Settings > Team: the people in this company and what they can do. */
export default function TeamManager() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: billing } = useBilling();
  const full = billing?.limits.users != null && billing.usage.users >= billing.limits.users;
  const { user: me } = useAuth();
  const { data: users = [] } = useQuery({ queryKey: ["users"], queryFn: () => apiClient.get("/users").then((r) => r.data) });
  const [draft, setDraft] = useState(BLANK);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["users"] });
    queryClient.invalidateQueries({ queryKey: ["team"] });
    queryClient.invalidateQueries({ queryKey: ["billing"] });
    queryClient.invalidateQueries({ queryKey: ["onboarding"] });
  };
  const create = useMutation({
    mutationFn: () => apiClient.post("/users", draft),
    onSuccess: () => {
      toast.success(t("team.added"), { description: t("team.addedHint", { email: draft.email }) });
      setDraft(BLANK);
      refresh();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const update = useMutation({
    mutationFn: ({ id, ...body }) => apiClient.patch(`/users/${id}`, body),
    onSuccess: () => {
      toast.success(t("team.updated"));
      refresh();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <section className="card p-4 sm:p-6">
      <h2 className="mb-1 text-base font-semibold text-zinc-900">{t("team.title")}</h2>
      <p className="mb-4 text-sm text-zinc-500">{t("team.intro")}</p>

      <ul className="divide-y divide-zinc-100 rounded-lg border border-zinc-200/80">
        {users.map((u) => {
          const self = u.id === me?.id;
          return (
            <li key={u.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <Avatar name={u.full_name} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-zinc-900">
                  {u.full_name} {self && <span className="text-xs font-normal text-zinc-400">· {t("messages.you")}</span>}
                </p>
                <p className="truncate text-xs text-zinc-500">{u.email}</p>
              </div>
              {!u.is_active && <StatusBadge status="inactive" />}
              <select
                className="input !h-9 !w-auto !py-0 !text-sm"
                aria-label={t("team.role")}
                value={u.role}
                disabled={self}
                onChange={(e) => update.mutate({ id: u.id, role: e.target.value })}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {t(`role.${r}`)}
                  </option>
                ))}
              </select>
              {!self && (
                <Button variant="secondary" className="!h-9 !px-3 !text-xs" onClick={() => update.mutate({ id: u.id, is_active: !u.is_active })}>
                  {t(u.is_active ? "team.deactivate" : "team.reactivate")}
                </Button>
              )}
            </li>
          );
        })}
      </ul>

      <form
        className={`mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 ${full ? "[&_input]:opacity-60 [&_select]:opacity-60" : ""}`}
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div className="sm:col-span-2">
          <SeatsPanel billing={billing} />
        </div>
        <p className="text-sm font-medium text-zinc-800 sm:col-span-2">{t("team.addTitle")}</p>
        <label className="block">
          <span className="label">{t("team.fullName")}</span>
          <input className="input" required value={draft.full_name} onChange={(e) => setDraft({ ...draft, full_name: e.target.value })} />
        </label>
        <label className="block">
          <span className="label">{t("login.email")}</span>
          <input className="input" type="email" autoCapitalize="none" required value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} />
        </label>
        <label className="block">
          <span className="label">{t("team.role")}</span>
          <select className="input" value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value })}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {t(`role.${r}`)} · {t(`team.roleHint.${r}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="label">{t("team.tempPassword")}</span>
          <input className="input" type="text" minLength={8} required autoComplete="off" value={draft.password} onChange={(e) => setDraft({ ...draft, password: e.target.value })} />
          <span className="mt-1.5 block text-xs text-zinc-500">{t("team.tempPasswordHint")}</span>
        </label>
        <div className="flex justify-end sm:col-span-2">
          <button type="submit" className="btn btn-primary" disabled={create.isPending || full}>
            {full ? t("team.seats.addSeatsFirst") : t("team.add")}
          </button>
        </div>
      </form>
    </section>
  );
}
