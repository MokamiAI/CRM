import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { errorMessage } from "../utils/format";
import { Button, Field } from "./ui";

// What a free onboarding session covers, in the order we go through it.
export const ONBOARDING_COVERS = ["setup", "import", "quoteToPay", "connect"];
// The subject of the ticket a request opens (when there are no open times),
// so the request can be recognised later as "already asked".
export const ONBOARDING_SUBJECT = "Onboarding request";
const OPEN_TICKET = ["open", "in_progress", "waiting"];

export const useSlots = () => useQuery({ queryKey: ["slots"], queryFn: () => apiClient.get("/bookings/slots").then((r) => r.data) });
const useBookings = () => useQuery({ queryKey: ["bookings"], queryFn: () => apiClient.get("/bookings").then((r) => r.data) });
const useTickets = () => useQuery({ queryKey: ["tickets"], queryFn: () => apiClient.get("/support/tickets").then((r) => r.data) });

/** Has this company already booked or asked for onboarding? */
export function useOnboardingStatus() {
  const { data: bookings } = useBookings();
  const { data: tickets } = useTickets();
  const booked = (bookings ?? []).find((b) => b.topic === "onboarding" && b.status === "booked" && new Date(b.ends_at) > new Date());
  const requested = (tickets ?? []).find((t) => t.subject === ONBOARDING_SUBJECT && OPEN_TICKET.includes(t.status));
  return { booked, requested, loading: !bookings || !tickets };
}

/** The checklist of what the session covers. */
export function OnboardingCovers({ className = "" }) {
  const { t } = useTranslation();
  return (
    <ul className={`grid gap-2 sm:grid-cols-2 ${className}`} data-testid="onboarding-covers">
      {ONBOARDING_COVERS.map((key) => (
        <li key={key} className="flex gap-2.5 rounded-xl bg-white p-3 ring-1 ring-inset ring-zinc-200/70">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={2} className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" aria-hidden="true">
            <path d="m3.5 8.5 3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="min-w-0">
            <span className="block text-sm font-medium text-zinc-900">{t(`onboarding.covers.${key}.title`)}</span>
            <span className="block text-xs leading-relaxed text-zinc-500">{t(`onboarding.covers.${key}.body`)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Dashboard offer for a new company: what onboarding covers and the way
 *  to ask for it. Once booked or asked for, it says so instead. */
export function OnboardingOffer() {
  const { t, i18n } = useTranslation();
  const { data: slots } = useSlots();
  const { booked, requested, loading } = useOnboardingStatus();
  const when = useMemo(() => new Intl.DateTimeFormat(i18n.language, { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }), [i18n.language]);
  if (loading) return null;
  return (
    <div className="border-t border-zinc-100 bg-indigo-50/40 px-5 py-4" data-testid="onboarding-offer">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-zinc-900">{t("onboarding.title")}</h3>
          <p className="mt-0.5 text-sm text-zinc-600">{t("onboarding.intro", { minutes: slots?.slot_minutes ?? 45 })}</p>
        </div>
        {booked ? (
          <Link to="/support?tab=sessions" className="btn btn-secondary !h-9 shrink-0 !text-sm">
            {t("onboarding.seeBooking")}
          </Link>
        ) : (
          !requested && (
            <Link to="/support?tab=sessions&topic=onboarding" className="btn btn-primary !h-9 shrink-0 !text-sm">
              {t("onboarding.request")}
            </Link>
          )
        )}
      </div>
      {booked ? (
        <p className="mt-3 rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800 ring-1 ring-inset ring-emerald-200/70" role="status">
          {t("onboarding.bookedFor", { when: when.format(new Date(booked.starts_at)) })}
        </p>
      ) : requested ? (
        <p className="mt-3 rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800 ring-1 ring-inset ring-emerald-200/70" role="status">
          {t("onboarding.requested")}
        </p>
      ) : (
        <OnboardingCovers className="mt-3" />
      )}
    </div>
  );
}

/** No open times to book: ask for onboarding instead. It opens a ticket
 *  with the team, who reply with a time. */
export function OnboardingRequestForm() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [times, setTimes] = useState("");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [missing, setMissing] = useState(false);
  const send = useMutation({
    mutationFn: () => {
      const covers = ONBOARDING_COVERS.map((k) => `- ${t(`onboarding.covers.${k}.title`, { lng: "en" })}`).join("\n");
      const body = [
        `${user?.full_name ?? "Someone"} would like an onboarding session.`,
        `Preferred days and times: ${times.trim()}`,
        phone.trim() && `Phone / WhatsApp: ${phone.trim()}`,
        notes.trim() && `Notes: ${notes.trim()}`,
        "",
        "Onboarding covers:",
        covers,
      ]
        .filter((line) => line !== false && line !== "")
        .join("\n");
      return apiClient.post("/support/tickets", { subject: ONBOARDING_SUBJECT, category: "question", urgency: "normal", body }).then((r) => r.data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      toast.success(t("onboarding.sent"), { description: t("onboarding.sentHint") });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <form
      className="space-y-4 rounded-xl bg-zinc-50 p-4 ring-1 ring-inset ring-zinc-200/70"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (!times.trim()) {
          setMissing(true);
          document.getElementById("onboarding-times")?.focus();
          return;
        }
        send.mutate();
      }}
      data-testid="onboarding-request"
    >
      <div>
        <h3 className="text-sm font-semibold text-zinc-900">{t("onboarding.requestTitle")}</h3>
        <p className="mt-0.5 text-sm text-zinc-600">{t("onboarding.requestIntro")}</p>
      </div>
      <Field label={t("onboarding.times")}>
        <textarea
          id="onboarding-times"
          className="input"
          rows={2}
          maxLength={500}
          value={times}
          aria-invalid={missing && !times.trim() ? true : undefined}
          aria-describedby={missing && !times.trim() ? "onboarding-times-error" : undefined}
          onChange={(e) => setTimes(e.target.value)}
          placeholder={t("onboarding.timesPlaceholder")}
        />
        {missing && !times.trim() && (
          <span id="onboarding-times-error" className="mt-1.5 block text-xs font-medium text-red-700">
            {t("onboarding.timesRequired")}
          </span>
        )}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("onboarding.phone")}>
          <input className="input" type="tel" autoComplete="tel" maxLength={50} value={phone} onChange={(e) => setPhone(e.target.value)} />
        </Field>
        <Field label={t("sessions.notes")}>
          <input className="input" maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder={t("sessions.notesPlaceholder")} />
        </Field>
      </div>
      <div className="flex justify-end">
        <Button type="submit" disabled={send.isPending}>
          {send.isPending ? t("common.saving") : t("onboarding.request")}
        </Button>
      </div>
    </form>
  );
}
