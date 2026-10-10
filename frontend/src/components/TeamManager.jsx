import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useBilling } from "../hooks/useApi";
import { errorMessage } from "../utils/format";
import { Avatar, Button, StatusBadge } from "./ui";

const ROLES = ["admin", "manager", "staff", "viewer"];
const BLANK = { full_name: "", email: "", role: "staff", password: "" };

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
        className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div className="flex flex-wrap items-baseline justify-between gap-2 sm:col-span-2">
          <p className="text-sm font-medium text-zinc-800">{t("team.addTitle")}</p>
          {billing?.limits.users != null && (
            <span className={`text-xs tabular-nums ${full ? "font-semibold text-rose-600" : "text-zinc-500"}`}>
              {t("billing.seatsUsed", { used: billing.usage.users, limit: billing.limits.users })}
            </span>
          )}
        </div>
        {full && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-inset ring-amber-200/70 sm:col-span-2">
            {t("billing.seatsFull")}{" "}
            <Link to="/settings?tab=billing" className="font-medium underline underline-offset-2">
              {t("billing.seePlans")}
            </Link>
          </p>
        )}
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
          <button type="submit" className="btn btn-primary" disabled={create.isPending}>
            {t("team.add")}
          </button>
        </div>
      </form>
    </section>
  );
}
