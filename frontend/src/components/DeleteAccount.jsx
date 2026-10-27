import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { useCompany } from "../hooks/useApi";
import { errorMessage } from "../utils/format";
import { Button, Field } from "./ui";

/** "Delete my account" (Settings > General, and My profile). The only admin
 *  of a company deletes the company and everything in it, after typing its
 *  name; anyone else just leaves it. Their password confirms either way. */
export default function DeleteAccount({ bare = false }) {
  const { t } = useTranslation();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const { data: company } = useCompany();
  const { data: check } = useQuery({ queryKey: ["delete-account"], queryFn: () => apiClient.get("/auth/delete-account").then((r) => r.data) });
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const whole = Boolean(check?.whole_company);
  const companyName = company?.company_name ?? "";
  const ready = password && (!whole || name.trim().toLowerCase() === companyName.trim().toLowerCase());

  const remove = useMutation({
    mutationFn: () => apiClient.post("/auth/delete-account", { password, company_name: whole ? name : null }).then((r) => r.data),
    onSuccess: async (data) => {
      toast.success(t(data.deleted === "company" ? "deleteAccount.doneCompany" : "deleteAccount.doneAccount"));
      await logout();
      navigate("/", { replace: true });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (check && !check.allowed) return null; // YGT's own admins

  return (
    <section className={bare ? "border-t border-zinc-200 pt-5" : "card p-4 sm:p-6"}>
      <h2 className="text-base font-semibold text-zinc-900">{t("deleteAccount.title")}</h2>
      <p className="mt-1 text-sm text-zinc-600">{t(whole ? "deleteAccount.introCompany" : "deleteAccount.introAccount", { company: companyName })}</p>
      {!open ? (
        <Button variant="secondary" className="mt-4 !text-red-700 hover:!bg-red-50" onClick={() => setOpen(true)}>
          {t("deleteAccount.start")}
        </Button>
      ) : (
        <form
          className="mt-4 space-y-4 rounded-xl bg-red-50/60 p-4 ring-1 ring-inset ring-red-200"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) remove.mutate();
          }}
        >
          <p className="text-sm font-medium text-red-900">{t(whole ? "deleteAccount.warnCompany" : "deleteAccount.warnAccount", { company: companyName })}</p>
          {whole && (
            <Field label={t("deleteAccount.typeName", { company: companyName })}>
              <input className="input" autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} placeholder={companyName} />
            </Field>
          )}
          <Field label={t("deleteAccount.password")}>
            <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <div className="flex flex-wrap gap-2">
            <button type="submit" disabled={!ready || remove.isPending} className="btn bg-red-600 text-white hover:bg-red-700 disabled:opacity-50">
              {remove.isPending ? t("deleteAccount.deleting") : t(whole ? "deleteAccount.confirmCompany" : "deleteAccount.confirmAccount")}
            </button>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
