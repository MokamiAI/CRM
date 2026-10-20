import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { Field } from "./ui";

export default function MeetingFields({ value, onChange, dealId, customerId, contactId, timezone, enabled }) {
  const { t } = useTranslation();
  const linked = Boolean(dealId || customerId || contactId);
  const contact = useQuery({
    queryKey: ["meeting-contact", dealId, customerId, contactId],
    queryFn: () => apiClient.get("/meetings/contact", { params: { deal_id: dealId, customer_id: customerId, contact_id: contactId } }).then((r) => r.data),
    enabled: enabled && linked,
  });
  useEffect(() => {
    if (!contact.data) return;
    onChange((current) => ({ ...current, attendee_name: contact.data.name || current.attendee_name, attendee_email: contact.data.email || current.attendee_email }));
  }, [contact.data, onChange]);
  const set = (key) => (event) => onChange((current) => ({ ...current, [key]: event.target.value }));
  return (
    <fieldset className="space-y-3 rounded-xl border border-blue-100 bg-blue-50/40 p-4">
      <legend className="px-1 text-sm font-semibold text-zinc-900">{t("meeting.invitation", "Meeting invitation")}</legend>
      <p className="text-xs leading-relaxed text-zinc-600">{linked ? t("meeting.contactHelp", "The workspace's contact person receives this invitation. Add missing details below; a missing contact email is saved back to their record.") : t("meeting.standaloneHelp", "This meeting has no workspace. Enter the attendee's name and email to send an invitation.")}</p>
      {contact.isFetching && <p className="text-xs text-zinc-500">{t("meeting.loadingContact", "Loading contact person...")}</p>}
      {contact.isError && <p role="alert" className="text-sm text-red-700">{t("meeting.contactError", "The contact could not be loaded.")} <button type="button" className="underline" onClick={() => contact.refetch()}>{t("common.retry", "Try again")}</button></p>}
      <Field label={t("meeting.attendeeName", "Attendee name")}>
        <input className="input" required maxLength={241} value={value.attendee_name || ""} onChange={set("attendee_name")} readOnly={Boolean(contact.data?.name)} />
      </Field>
      <Field label={t("meeting.attendeeEmail", "Contact person's email")} hint={linked && !contact.data?.email ? t("meeting.emailMissing", "The contact person's email is missing. Please add it to send the invitation.") : undefined}>
        <input className="input" required type="email" maxLength={255} value={value.attendee_email || ""} onChange={set("attendee_email")} readOnly={Boolean(contact.data?.email)} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("meeting.duration", "Duration (minutes)")}>
          <select className="input" value={value.duration_minutes} onChange={(e) => onChange((current) => ({ ...current, duration_minutes: Number(e.target.value) }))}>
            {[15, 30, 45, 60, 90, 120, 180, 240, 480].map((minutes) => <option key={minutes} value={minutes}>{minutes}</option>)}
          </select>
        </Field>
        <Field label={t("meeting.timezone", "Time zone")}><p className="py-2.5 text-sm text-zinc-700">{timezone || "Africa/Johannesburg"}</p></Field>
      </div>
      <Field label={t("meeting.location", "Location or meeting link (optional)")}>
        <input className="input" maxLength={500} value={value.location || ""} onChange={set("location")} placeholder={t("meeting.locationHint", "Office address or video call link")} />
      </Field>
      <p className="text-xs leading-relaxed text-zinc-500">{t("meeting.sendHelp", "Saving sends an email invitation and holds the time in YGT. The attendee can accept, decline with a reason, or suggest another time. Changes send an updated invitation.")}</p>
    </fieldset>
  );
}
