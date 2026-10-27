import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { useCompany } from "../hooks/useApi";
import { errorMessage } from "../utils/format";
import Sheet from "./Sheet";
import { Avatar, Button, Field } from "./ui";
import DeleteAccount from "./DeleteAccount";

const MAX = 1000;

/** A plain-text signature box with a preview of the email's last lines. */
export function SignatureEditor({ id, value, onChange, placeholder, fallback, greeting, onStarter }) {
  const { t } = useTranslation();
  const lines = (value.trim() ? value : fallback).split("\n");
  return (
    <div className="space-y-3">
      <div>
        <textarea
          id={id}
          className="input min-h-[7.5rem] resize-y font-[inherit] leading-relaxed"
          rows={5}
          maxLength={MAX}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
        <div className="mt-1 flex items-center justify-between gap-3 text-xs text-zinc-500">
          {onStarter ? (
            <button type="button" className="font-medium text-indigo-600 hover:text-indigo-700" onClick={onStarter}>
              {t("signature.starter")}
            </button>
          ) : (
            <span />
          )}
          <span className="tabular-nums">
            {value.length}/{MAX}
          </span>
        </div>
      </div>
      <figure className="rounded-xl bg-zinc-50 p-4 ring-1 ring-inset ring-zinc-200/70">
        <figcaption className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{t("signature.preview")}</figcaption>
        <div className="rounded-lg bg-white p-4 text-[14px] leading-relaxed text-zinc-700 shadow-sm ring-1 ring-zinc-200/60">
          <p className="text-zinc-400">{t("signature.previewBody")}</p>
          <p className="mt-3">
            {greeting && (
              <>
                {greeting}
                <br />
              </>
            )}
            {lines.map((line, i) => (
              <span key={i}>
                {line}
                {i < lines.length - 1 && <br />}
              </span>
            ))}
          </p>
        </div>
      </figure>
    </div>
  );
}

/** Each person's own details: name and the signature on emails they send
 *  from Messages. Opened from their name in the sidebar (or More on phones). */
export function ProfileSheet({ open, onClose }) {
  const { t } = useTranslation();
  const { user, updateProfile } = useAuth();
  const { data: company } = useCompany();
  const [name, setName] = useState("");
  const [signature, setSignature] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !user) return;
    setName(user.full_name || "");
    setSignature(user.email_signature || "");
  }, [open, user]);

  const companyName = company?.company_name || "";
  const starter = () => setSignature([name.trim(), `${t(`role.${user?.role}`)} · ${companyName}`, user?.email].filter(Boolean).join("\n"));

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    try {
      await updateProfile({ full_name: name.trim(), email_signature: signature });
      toast.success(t("profile.saved"));
      onClose();
    } catch (error) {
      toast.error(errorMessage(error, t("profile.saveFailed")));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t("profile.title")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="profile-form" disabled={saving || !name.trim()}>
            {saving ? t("common.saving") : t("profile.save")}
          </Button>
        </div>
      }
    >
      <form id="profile-form" onSubmit={save} className="space-y-5">
        <div className="flex items-center gap-3">
          <Avatar name={name || user?.email || "?"} />
          <div className="min-w-0">
            <p className="truncate font-medium text-zinc-900">{name || user?.email}</p>
            <p className="truncate text-sm text-zinc-500">{user?.email}</p>
          </div>
        </div>
        <Field label={t("profile.name")}>
          <input className="input" required maxLength={255} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div>
          <label htmlFor="profile-signature" className="label">
            {t("signature.yours")}
          </label>
          <p className="mb-2 text-sm text-zinc-500">{t("signature.yoursHint")}</p>
          <SignatureEditor
            id="profile-signature"
            value={signature}
            onChange={setSignature}
            placeholder={t("signature.yoursPlaceholder")}
            fallback={company?.email_signature || `${name || user?.full_name || ""}\n${companyName}`}
            onStarter={starter}
          />
        </div>
      </form>
      <div className="mt-8">
        <DeleteAccount bare />
      </div>
    </Sheet>
  );
}
