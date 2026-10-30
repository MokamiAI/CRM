import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { errorMessage } from "../utils/format";

/** For people who haven't said yet: may YGT send them tips, news and
 *  offers (POPIA s69)? Asked once; the answer can change in their profile. */
export default function MarketingConsentBanner() {
  const { t } = useTranslation();
  const { user, updateProfile } = useAuth();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  if (!user || user.marketing_opt_in != null || user.is_platform_admin) return null;

  async function answer(agreed) {
    setBusy(true);
    try {
      await updateProfile({ marketing_opt_in: agreed, marketing_source: "prompt" });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      toast.success(t(agreed ? "consent.savedYes" : "consent.savedNo"));
    } catch (err) {
      toast.error(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl bg-indigo-50/70 px-4 py-3 ring-1 ring-inset ring-indigo-200/70" role="region" aria-labelledby="consent-title">
      <div className="min-w-0 flex-1 basis-72">
        <p id="consent-title" className="text-sm font-semibold text-indigo-950">{t("consent.title")}</p>
        <p className="text-sm text-indigo-900/80">{t("consent.body")}</p>
      </div>
      <div className="flex gap-2">
        <button type="button" className="btn btn-secondary !h-9 !text-sm" disabled={busy} onClick={() => answer(false)}>
          {t("consent.no")}
        </button>
        <button type="button" className="btn btn-primary !h-9 !text-sm" disabled={busy} onClick={() => answer(true)}>
          {t("consent.yes")}
        </button>
      </div>
    </div>
  );
}
