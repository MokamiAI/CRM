import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCompany } from "../hooks/useApi";
import { Button } from "./ui";

const KINDS = ["promotion", "launch", "newsletter", "event", "winback", "thanks", "festive", "review"];

/** "What do you want to do?": a ready-written campaign for each common
 *  purpose. Picking one fills the subject, preview text, message and button
 *  text ({name} stays for each recipient's name; [brackets] are for the
 *  sender to fill in). Asks first if there's already a message. */
export default function CampaignTemplates({ form, onUse }) {
  const { t } = useTranslation();
  const { data: company } = useCompany();
  const [pending, setPending] = useState(null);

  function fill(kind) {
    const text = (key) => t(`campaignTemplates.items.${kind}.${key}`).replaceAll("{company}", company?.company_name || "us");
    onUse({ name: text("name"), subject: text("subject"), preheader: text("preheader"), body: text("body"), cta_text: text("cta") });
    setPending(null);
  }

  function pick(kind) {
    if (form.subject.trim() || form.body.trim()) setPending(kind);
    else fill(kind);
  }

  return (
    <section className="card p-4 sm:p-5">
      <p className="label !mb-0">{t("campaignTemplates.title")}</p>
      <p className="mt-0.5 text-xs text-zinc-500">{t("campaignTemplates.hint")}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {KINDS.map((kind) => (
          <button
            key={kind}
            type="button"
            onClick={() => pick(kind)}
            aria-pressed={pending === kind}
            className="pressable rounded-full bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 ring-1 ring-inset ring-zinc-200 transition-colors hover:bg-indigo-50 hover:text-indigo-700 hover:ring-indigo-200 aria-pressed:bg-indigo-50 aria-pressed:text-indigo-700 aria-pressed:ring-indigo-300"
          >
            {t(`campaignTemplates.items.${kind}.label`)}
          </button>
        ))}
      </div>
      {pending && (
        <div className="mt-4 rounded-xl bg-amber-50 p-3 ring-1 ring-inset ring-amber-200/80" role="alert">
          <p className="text-sm font-semibold text-amber-950">{t("campaignTemplates.replaceTitle")}</p>
          <p className="mt-0.5 text-sm text-amber-900/85">{t("campaignTemplates.replaceBody", { label: t(`campaignTemplates.items.${pending}.label`) })}</p>
          <div className="mt-3 flex gap-2">
            <Button className="!h-9 !text-sm" onClick={() => fill(pending)}>
              {t("campaignTemplates.replace")}
            </Button>
            <Button variant="secondary" className="!h-9 !text-sm" onClick={() => setPending(null)}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
