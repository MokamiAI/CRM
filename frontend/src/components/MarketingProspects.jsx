import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { useCompany, useProspects } from "../hooks/useApi";
import { errorMessage, formatDate } from "../utils/format";
import Sheet from "./Sheet";
import { Button, EmptyState, ErrorState, Field, ListSkeleton } from "./ui";

/*
 * Prospects and marketing consent (POPIA s69). A prospect isn't a customer
 * yet, so campaigns only reach them once they've agreed. Agreement is
 * ticked with how it was given, or asked for once with a personal email
 * whose yes/no link records the answer.
 */

// Ways people commonly agree, offered as a quick pick; anything else can be typed.
const SOURCES = ["phone", "inPerson", "form", "email"];

function status(p) {
  if (p.marketing_consent_at) return "agreed";
  if (p.marketing_opt_out) return "declined";
  if (p.consent_invited_at) return "invited";
  return "notAsked";
}

const TONE = {
  agreed: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  invited: "bg-amber-50 text-amber-700 ring-amber-600/20",
  declined: "bg-zinc-100 text-zinc-600 ring-zinc-500/20",
  notAsked: "bg-zinc-50 text-zinc-600 ring-zinc-500/15",
};

export default function MarketingProspects({ adding, onAdded }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const { data = [], isLoading, isError, refetch } = useProspects();
  const [agreeing, setAgreeing] = useState(null);
  const [inviting, setInviting] = useState(null);

  return (
    <div className="space-y-3">
      <p className="rounded-xl bg-indigo-50/70 p-3 text-sm text-indigo-950 ring-1 ring-inset ring-indigo-600/10">{t("prospects.lawNote")}</p>
      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : data.length === 0 ? (
        <EmptyState title={t("prospects.empty")} description={t("prospects.emptyHint")} action={canWrite && <Button onClick={() => onAdded?.("open")}>{t("prospects.add")}</Button>} />
      ) : (
        <ul className="card divide-y divide-zinc-100 overflow-hidden">
          {data.map((p) => (
            <Row key={p.id} prospect={p} canWrite={canWrite} onAgree={() => setAgreeing(p)} onInvite={() => setInviting(p)} />
          ))}
        </ul>
      )}
      <AddProspectSheet open={adding} onClose={() => onAdded?.("close")} />
      <AgreeSheet prospect={agreeing} onClose={() => setAgreeing(null)} />
      <InviteSheet prospect={inviting} onClose={() => setInviting(null)} />
    </div>
  );
}

function Row({ prospect: p, canWrite, onAgree, onInvite }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const state = status(p);
  const withdraw = useMutation({
    mutationFn: () => apiClient.put(`/marketing/prospects/${p.id}/consent`, { agreed: false }).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["prospects"] }),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const detail =
    state === "agreed"
      ? t("prospects.agreedOn", { date: formatDate(p.marketing_consent_at), source: p.marketing_consent_source })
      : state === "invited"
        ? t("prospects.invitedOn", { date: formatDate(p.consent_invited_at) })
        : state === "declined"
          ? t("prospects.declinedHint")
          : p.recipient_email
            ? t("prospects.notAskedHint")
            : t("prospects.noEmail");
  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate font-medium text-zinc-900">{p.name}</p>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONE[state]}`}>{t(`prospects.status.${state}`)}</span>
        </div>
        {p.recipient_email && <p className="truncate text-sm text-zinc-500">{p.recipient_email}</p>}
        <p className="mt-0.5 text-xs text-zinc-500">{detail}</p>
      </div>
      {canWrite && (
        <div className="flex shrink-0 flex-wrap gap-2">
          {state === "agreed" ? (
            <Button variant="secondary" className="!h-9 !text-sm" disabled={withdraw.isPending} onClick={() => withdraw.mutate()}>
              {t("prospects.withdraw")}
            </Button>
          ) : (
            <>
              {state === "notAsked" && p.recipient_email && (
                <Button variant="secondary" className="!h-9 !text-sm" onClick={onInvite}>
                  {t("prospects.invite")}
                </Button>
              )}
              <Button variant="secondary" className="!h-9 !text-sm" onClick={onAgree}>
                {t("prospects.markAgreed")}
              </Button>
            </>
          )}
        </div>
      )}
    </li>
  );
}

function AddProspectSheet({ open, onClose }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const blank = { name: "", email: "", phone: "" };
  const [form, setForm] = useState(blank);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const save = useMutation({
    mutationFn: () => apiClient.post("/prospects", { name: form.name.trim(), email: form.email.trim() || null, phone: form.phone.trim() || null }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prospects"] });
      toast.success(t("prospects.added"));
      setForm(blank);
      onClose();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t("prospects.add")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="prospect-form" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? t("common.saving") : t("common.save")}
          </button>
        </>
      }
    >
      <form
        id="prospect-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label={t("prospects.name")}>
          <input className="input" required minLength={2} maxLength={255} value={form.name} onChange={set("name")} autoFocus />
        </Field>
        <Field label={t("contact.email")}>
          <input className="input" type="email" value={form.email} onChange={set("email")} />
        </Field>
        <Field label={t("contact.phone")}>
          <input className="input" type="tel" maxLength={50} value={form.phone} onChange={set("phone")} />
        </Field>
        <p className="text-xs text-zinc-500">{t("prospects.addNote")}</p>
      </form>
    </Sheet>
  );
}

function AgreeSheet({ prospect, onClose }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [source, setSource] = useState("");
  const [last, setLast] = useState(null);
  if (prospect !== last) {
    setLast(prospect);
    setSource("");
  }
  const save = useMutation({
    mutationFn: () => apiClient.put(`/marketing/prospects/${prospect.id}/consent`, { agreed: true, source }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prospects"] });
      toast.success(t("prospects.agreedSaved", { name: prospect.name }));
      onClose();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <Sheet
      open={!!prospect}
      onClose={onClose}
      title={t("prospects.markAgreed")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="agree-form" className="btn btn-primary" disabled={save.isPending || !source.trim()}>
            {t("common.save")}
          </button>
        </>
      }
    >
      <form
        id="agree-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <p className="text-sm text-zinc-600">{t("prospects.agreeIntro", { name: prospect?.name })}</p>
        <div className="flex flex-wrap gap-2">
          {SOURCES.map((k) => {
            const label = t(`prospects.sources.${k}`);
            return (
              <button
                key={k}
                type="button"
                onClick={() => setSource(label)}
                className={`rounded-full px-3 py-1.5 text-sm ring-1 ring-inset ${source === label ? "bg-indigo-50 text-indigo-700 ring-indigo-600" : "text-zinc-700 ring-zinc-200 hover:bg-zinc-50"}`}
              >
                {label}
              </button>
            );
          })}
        </div>
        <Field label={t("prospects.howAgreed")} hint={t("prospects.howAgreedHint")}>
          <input className="input" required maxLength={200} value={source} onChange={(e) => setSource(e.target.value)} />
        </Field>
      </form>
    </Sheet>
  );
}

function InviteSheet({ prospect, onClose }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: company } = useCompany();
  const name = company?.company_name ?? "";
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [last, setLast] = useState(null);
  if (prospect !== last) {
    setLast(prospect);
    setSubject(t("prospects.inviteSubject", { company: name }));
    setMessage(t("prospects.inviteMessage", { company: name }));
  }
  const send = useMutation({
    mutationFn: () => apiClient.post(`/marketing/prospects/${prospect.id}/invite`, { subject, message }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prospects"] });
      toast.success(t("prospects.invited", { email: prospect.recipient_email }));
      onClose();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <Sheet
      open={!!prospect}
      onClose={onClose}
      title={t("prospects.invite")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="invite-form" className="btn btn-primary" disabled={send.isPending}>
            {send.isPending ? t("common.sending") : t("prospects.sendInvite")}
          </button>
        </>
      }
    >
      <form
        id="invite-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          send.mutate();
        }}
      >
        <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-950 ring-1 ring-inset ring-amber-600/15">{t("prospects.inviteOnce", { email: prospect?.recipient_email })}</p>
        <Field label={t("prospects.subject")}>
          <input className="input" maxLength={200} value={subject} onChange={(e) => setSubject(e.target.value)} />
        </Field>
        <Field label={t("prospects.message")} hint={t("prospects.messageHint")}>
          <textarea className="input min-h-48" required minLength={10} maxLength={5000} value={message} onChange={(e) => setMessage(e.target.value)} />
        </Field>
        <p className="text-xs text-zinc-500">{t("prospects.inviteAdds")}</p>
      </form>
    </Sheet>
  );
}
