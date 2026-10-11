import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { errorMessage } from "../utils/format";

/** Until someone clicks the link we emailed, a quiet reminder with a resend button. */
export default function VerifyEmailBanner() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  if (!user || user.email_verified_at) return null;

  async function resend() {
    setBusy(true);
    try {
      await apiClient.post("/auth/verify-email/resend");
      toast.success(t("verify.resent"), { description: user.email });
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl bg-indigo-50/70 px-4 py-3 ring-1 ring-inset ring-indigo-200/70" role="status">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-indigo-950">{t("verify.bannerTitle")}</p>
        <p className="text-sm text-indigo-900/80">{t("verify.bannerBody", { email: user.email })}</p>
      </div>
      <button type="button" className="btn btn-secondary !h-9 !text-sm" disabled={busy} onClick={resend}>
        {busy ? t("common.sending") : t("verify.resend")}
      </button>
    </div>
  );
}
