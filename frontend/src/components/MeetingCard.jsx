import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import apiClient from "../services/apiClient";
import { errorMessage } from "../utils/format";
import { refreshTask } from "./TaskChecklist";

export const meetingLabel = (status, t) => t(`meeting.status.${status}`, {
  invited: "Awaiting response", accepted: "Accepted", declined: "Declined", proposed: "New time proposed", cancelled: "Cancelled", internal: "Internal meeting",
}[status] || status);

export default function MeetingCard({ activity, canWrite }) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const meeting = activity.meeting;
  const decide = useMutation({
    mutationFn: ({ action, ...body }) => apiClient.post(`/meetings/${activity.id}/${action}`, body).then((r) => r.data),
    onSuccess: () => { refreshTask(queryClient); queryClient.invalidateQueries({ queryKey: ["meeting-calendar"] }); toast.success(t("meeting.updated", "Meeting updated")); },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const download = useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.get(`/meetings/${activity.id}/calendar.ics`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a"); a.href = url; a.download = "meeting.ics"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  if (!meeting) return null;
  const format = (at) => new Intl.DateTimeFormat(i18n.language, { timeZone: meeting.timezone, dateStyle: "medium", timeStyle: "short" }).format(new Date(at));
  const canDecide = canWrite && (user?.id === meeting.organizer_id || ["admin", "manager"].includes(user?.role));
  return (
    <section className="space-y-3 rounded-xl border border-blue-100 bg-blue-50/40 p-4" aria-label={t("meeting.details", "Meeting details")}>
      <h3 className="text-sm font-semibold text-zinc-900">{meetingLabel(meeting.status, t)}</h3>
      <p className="break-words text-sm text-zinc-700">{meeting.attendee_name}<br /><a className="text-blue-700 hover:underline" href={`mailto:${meeting.attendee_email}`}>{meeting.attendee_email}</a></p>
      <p className="text-sm text-zinc-700">{format(meeting.starts_at)}<br /><span className="text-xs text-zinc-500">{meeting.timezone}</span></p>
      {meeting.location && <p className="break-words text-sm text-zinc-700">{meeting.location}</p>}
      {meeting.response_reason && <p className="whitespace-pre-line rounded-lg bg-white p-3 text-sm text-zinc-700">{meeting.response_reason}</p>}
      {meeting.proposed_start && <div className="space-y-3 border-t border-blue-100 pt-3">
        <p className="text-sm font-medium text-zinc-900">{t("meeting.proposedTime", "Suggested time")}: {format(meeting.proposed_start)}</p>
        <p className="text-xs text-zinc-600">{t("meeting.heldHelp", "Both times are held in YGT until you decide. Approving moves the meeting and releases the old time.")}</p>
        {canDecide && <>
          <input className="input" aria-label={t("meeting.reviewNote", "Note to attendee (optional)")} maxLength={2000} placeholder={t("meeting.reviewNote", "Note to attendee (optional)")} value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-primary" disabled={decide.isPending} onClick={() => decide.mutate({ action: "proposal", accept: true, reason })}>{t("meeting.approveTime", "Approve new time")}</button>
            <button type="button" className="btn btn-secondary" disabled={decide.isPending} onClick={() => decide.mutate({ action: "proposal", accept: false, reason })}>{t("meeting.keepOriginal", "Offer original time")}</button>
          </div>
        </>}
      </div>}
      <div className="flex flex-wrap gap-2">
        {["invited", "accepted", "proposed"].includes(meeting.status) && <button type="button" className="btn btn-secondary" disabled={download.isPending} onClick={() => download.mutate()}>{t("meeting.addCalendar", "Add to my calendar")}</button>}
        {canDecide && !["cancelled", "declined"].includes(meeting.status) && <button type="button" className="min-h-11 px-2 text-sm font-medium text-red-700 hover:underline" disabled={decide.isPending} onClick={() => decide.mutate({ action: "cancel" })}>{t("meeting.cancelNotify", "Cancel and notify attendee")}</button>}
      </div>
    </section>
  );
}
