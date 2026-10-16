import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { errorMessage } from "../utils/format";

const HOUR = 3600 * 1000;

/** An unconfirmed account's deadline has passed (the server agrees: it
 *  refuses everything but sign-in and the link until it's confirmed). */
export function verificationOverdue(user) {
  return Boolean(user && !user.email_verified_at && user.verify_by && Date.now() >= new Date(user.verify_by).getTime());
}

function useResend(email) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  async function resend() {
    setBusy(true);
    try {
      await apiClient.post("/auth/verify-email/resend");
      toast.success(t("verify.resent"), { description: email });
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return { busy, resend };
}

/** Until someone clicks the link we emailed: a reminder with the time left
 *  to confirm (48 hours from sign-up) and a resend button. */
export default function VerifyEmailBanner() {
  const { t } = useTranslation();
  const { user, reloadUser } = useAuth();
  const { busy, resend } = useResend(user?.email);
  const [now, setNow] = useState(() => Date.now());
  const deadline = user?.verify_by ? new Date(user.verify_by).getTime() : null;
  // Tick each minute; at the deadline, re-check so the app can close.
  useEffect(() => {
    if (!deadline || user?.email_verified_at) return undefined;
    const timer = setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= deadline) reloadUser();
    }, 60 * 1000);
    return () => clearInterval(timer);
  }, [deadline, user?.email_verified_at, reloadUser]);
  if (!user || user.email_verified_at) return null;

  const hours = deadline ? Math.max(1, Math.ceil((deadline - now) / HOUR)) : null;
  const urgent = hours != null && hours <= 12;
  return (
    <div
      className={`mb-5 flex flex-wrap items-center gap-3 rounded-xl px-4 py-3 ring-1 ring-inset ${
        urgent ? "bg-amber-50 ring-amber-200/80" : "bg-indigo-50/70 ring-indigo-200/70"
      }`}
      role="status"
    >
      <div className="min-w-0 flex-1">
        <p className={`text-sm font-semibold ${urgent ? "text-amber-950" : "text-indigo-950"}`}>{t("verify.bannerTitle")}</p>
        <p className={`text-sm ${urgent ? "text-amber-900" : "text-indigo-900/80"}`}>
          {t("verify.bannerBody", { email: user.email })}
          {hours != null && <strong className="font-semibold"> {t("verify.hoursLeft", { count: hours })}</strong>}
        </p>
      </div>
      <button type="button" className="btn btn-secondary !h-9 !text-sm" disabled={busy} onClick={resend}>
        {busy ? t("common.sending") : t("verify.resend")}
      </button>
    </div>
  );
}

/** The 48 hours have passed without a confirmed email: this instead of the
 *  app until the link is clicked. Nothing is lost; it all opens again. */
export function VerifyGate() {
  const { t } = useTranslation();
  const { user, reloadUser, logout } = useAuth();
  const { busy, resend } = useResend(user.email);
  const [checking, setChecking] = useState(false);
  async function check() {
    setChecking(true);
    await reloadUser();
    setChecking(false);
    // Still here after the reload: the link hasn't been clicked yet.
    toast.message(t("verify.notYet"));
  }
  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-zinc-50 p-6">
      <div className="card w-full max-w-md p-6 text-center sm:p-8">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 ring-4 ring-indigo-50/60" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6">
            <rect x="3" y="5" width="18" height="14" rx="2" />
            <path d="m3.5 6.5 8.5 6.5 8.5-6.5" />
          </svg>
        </span>
        <h1 className="mt-4 text-xl font-semibold text-zinc-900">{t("verify.gateTitle")}</h1>
        <p className="mt-2 text-sm leading-relaxed text-zinc-600">{t("verify.gateBody", { email: user.email })}</p>
        <div className="mt-6 flex flex-col gap-2">
          <button type="button" className="btn btn-primary" disabled={checking} onClick={check}>
            {t("verify.gateDone")}
          </button>
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={resend}>
            {busy ? t("common.sending") : t("verify.resend")}
          </button>
          <button type="button" className="mt-1 text-sm font-medium text-zinc-500 hover:text-zinc-800" onClick={logout}>
            {t("nav.logout")}
          </button>
        </div>
      </div>
    </div>
  );
}
