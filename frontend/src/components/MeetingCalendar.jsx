import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useCompany } from "../hooks/useApi";
import { todayISO } from "../utils/format";
import { meetingLabel } from "./MeetingCard";

const addDays = (day, count) => { const date = new Date(day + "T00:00:00Z"); date.setUTCDate(date.getUTCDate() + count); return date.toISOString().slice(0, 10); };

export default function MeetingCalendar() {
  const { t, i18n } = useTranslation();
  const { data: company } = useCompany();
  const timezone = company?.default_timezone || "Africa/Johannesburg";
  const [start, setStart] = useState(todayISO());
  const [mine, setMine] = useState(true);
  const events = useQuery({ queryKey: ["meeting-calendar", start, mine], queryFn: () => apiClient.get("/meetings/calendar", { params: { start, end: addDays(start, 7), mine } }).then((r) => r.data), refetchInterval: 15000 });
  const key = (at) => new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(at));
  const time = (at) => new Intl.DateTimeFormat(i18n.language, { timeZone: timezone, hour: "2-digit", minute: "2-digit" }).format(new Date(at));
  return (
    <section className="mb-6 space-y-4 rounded-xl border border-zinc-200 bg-zinc-50/60 p-4" aria-label={t("meeting.calendar", "Meeting calendar")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="text-base font-semibold text-zinc-900">{t("meeting.calendar", "Meeting calendar")}</h2><p className="mt-1 text-xs text-zinc-500">{timezone}</p></div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn btn-secondary" onClick={() => setStart(addDays(start, -7))}>{t("meeting.previous", "Previous week")}</button>
          <input type="date" className="input w-auto" aria-label={t("meeting.weekStarting", "Week starting")} required value={start} onChange={(e) => e.target.value && setStart(e.target.value)} />
          <button type="button" className="btn btn-secondary" onClick={() => setStart(addDays(start, 7))}>{t("meeting.next", "Next week")}</button>
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm text-zinc-700"><input type="checkbox" className="h-4 w-4 rounded" checked={!mine} onChange={(e) => setMine(!e.target.checked)} />{t("meeting.wholeWorkspace", "Show the whole workspace")}</label>
      <p className="text-xs leading-relaxed text-zinc-600">{t("meeting.calendarHelp", "Invitations and proposed times hold space in YGT. Accepted meetings are confirmed. Events in other calendar apps are not checked.")}</p>
      {events.isError ? <p role="alert" className="text-sm text-red-700">{t("meeting.calendarError", "Could not load the calendar.")} <button className="underline" type="button" onClick={() => events.refetch()}>{t("common.retry", "Try again")}</button></p> : events.isLoading ? <p className="text-sm text-zinc-500">{t("common.loading", "Loading...")}</p> : (
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-7">
          {Array.from({ length: 7 }, (_, index) => {
            const day = addDays(start, index);
            const entries = (events.data || []).filter((event) => key(event.starts_at) <= day && key(new Date(new Date(event.ends_at).getTime() - 1)) >= day);
            return <div key={day} className="min-w-0 rounded-lg border border-zinc-200 bg-white p-3">
              <h3 className="mb-2 text-xs font-semibold text-zinc-700">{new Intl.DateTimeFormat(i18n.language, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(day + "T12:00:00Z"))}</h3>
              {entries.length ? <ul className="space-y-2">{entries.map((event) => <li key={`${event.activity_id}-${event.proposed}`}><Link className={`block break-words rounded-lg border p-2 text-xs ${event.status === "accepted" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-blue-200 bg-blue-50 text-blue-900"}`} to={`/activities?task=${event.activity_id}`}>
                <span className="block font-semibold">{time(event.starts_at)} - {time(event.ends_at)}</span><span className="mt-1 block font-medium">{event.subject}</span><span className="mt-1 block">{event.proposed ? t("meeting.proposedHold", "Proposed hold") : meetingLabel(event.status, t)}</span>
              </Link></li>)}</ul> : <p className="text-xs text-zinc-400">{t("meeting.free", "No meetings")}</p>}
            </div>;
          })}
        </div>
      )}
    </section>
  );
}
