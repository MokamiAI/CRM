import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { useTour } from "./Tour";

// Where each checklist item is done.
const LINKS = {
  company: "/settings",
  email: "/settings?tab=email",
  customer: "/customers",
  product: "/products",
  deal: "/deals?new=1",
  send: "/quotes/new",
  team: "/settings?tab=team",
  channels: "/settings?tab=whatsapp",
};

export function useChecklist() {
  return useQuery({ queryKey: ["onboarding"], queryFn: () => apiClient.get("/onboarding").then((r) => r.data) });
}

/** Dashboard card for new companies: what's left to set up, ticked off
 *  automatically from real data as people use the app. */
export default function GetStarted() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { start } = useTour();
  const { data } = useChecklist();
  const isAdmin = user?.role === "admin";
  const dismiss = useMutation({
    mutationFn: () => apiClient.post("/onboarding/dismiss").then((r) => r.data),
    onSuccess: (next) => queryClient.setQueryData(["onboarding"], next),
  });

  if (!data || data.dismissed) return null;
  const required = data.items.filter((i) => !i.optional);
  const doneCount = required.filter((i) => i.done).length;
  const allDone = doneCount === required.length;
  const pct = Math.round((doneCount / required.length) * 100);

  return (
    <section className="card overflow-hidden" data-tour="get-started">
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pb-3 pt-4">
        <div>
          <h2 className="text-base font-semibold text-zinc-900">{t(allDone ? "getStarted.doneTitle" : "getStarted.title")}</h2>
          <p className="mt-0.5 text-sm text-zinc-500">{t(allDone ? "getStarted.doneBody" : "getStarted.intro")}</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn btn-secondary !h-8 !px-3 !text-xs" onClick={start}>
            {t("getStarted.tour")}
          </button>
          {isAdmin && (
            <button type="button" className="btn btn-secondary !h-8 !px-3 !text-xs" onClick={() => dismiss.mutate()}>
              {t("getStarted.hide")}
            </button>
          )}
        </div>
      </div>
      <div className="px-5">
        <div className="flex items-center gap-3">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-100" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div className="brand-bg h-full rounded-full transition-[width] duration-500 ease-out" style={{ width: `${pct}%` }} />
          </div>
          <span className="shrink-0 text-xs font-medium tabular-nums text-zinc-600">{t("getStarted.progress", { done: doneCount, total: required.length })}</span>
        </div>
      </div>
      <ul className="mt-3 grid grid-cols-1 gap-px bg-zinc-100 sm:grid-cols-2">
        {data.items.map((item) => {
          const locked = item.admin_only && !isAdmin && !item.done;
          const content = (
            <>
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ring-1 ring-inset ${
                  item.done ? "bg-emerald-500 text-white ring-emerald-500" : "bg-white text-transparent ring-zinc-300"
                }`}
                aria-hidden="true"
              >
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={2.2} className="h-3 w-3">
                  <path d="m3.5 8.5 3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <span className="min-w-0 flex-1">
                <span className={`block text-sm font-medium ${item.done ? "text-zinc-400 line-through decoration-zinc-300" : "text-zinc-900"}`}>
                  {t(`getStarted.items.${item.key}.title`)}
                  {item.optional && <span className="ml-1.5 text-xs font-normal text-zinc-400">{t("channels.optional")}</span>}
                </span>
                {!item.done && (
                  <span className="block text-xs text-zinc-500">{locked ? t("getStarted.askAdmin") : t(`getStarted.items.${item.key}.hint`)}</span>
                )}
              </span>
              {!item.done && !locked && <span className="shrink-0 text-zinc-300" aria-hidden="true">›</span>}
            </>
          );
          return (
            <li key={item.key} className="bg-white">
              {item.done || locked ? (
                <div className="flex items-center gap-3 px-5 py-3">{content}</div>
              ) : (
                <Link to={LINKS[item.key]} className="flex items-center gap-3 px-5 py-3 transition-colors duration-150 hover:bg-zinc-50">
                  {content}
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
