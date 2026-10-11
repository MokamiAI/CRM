import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import Sheet from "../components/Sheet";
import { BackLink } from "../components/DocumentView";
import { Button, EmptyState, ErrorState, Field, FilterChips, ListSkeleton, PageHeader, PlusIcon } from "../components/ui";
import { errorMessage, formatDate, formatDateTime } from "../utils/format";
import { celebrate } from "../utils/motion";

const CATEGORIES = ["question", "problem", "billing", "feature", "account"];
const URGENCIES = ["low", "normal", "high"];
const TOPICS = ["onboarding", "training", "support", "billing", "other"];
const STATUS_TONE = {
  open: "bg-indigo-50 text-indigo-700 ring-indigo-200/70",
  in_progress: "bg-indigo-50 text-indigo-700 ring-indigo-200/70",
  waiting: "bg-amber-50 text-amber-800 ring-amber-200/70",
  resolved: "bg-emerald-50 text-emerald-700 ring-emerald-200/70",
  closed: "bg-zinc-100 text-zinc-600 ring-zinc-200",
};

export function TicketStatus({ status }) {
  const { t } = useTranslation();
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_TONE[status] ?? STATUS_TONE.closed}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {t(`support.status.${status}`)}
    </span>
  );
}

/** The Support tab: a company's tickets with YGT, and booking a session. */
export default function SupportPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "sessions" ? "sessions" : "tickets";
  const [newTicket, setNewTicket] = useState(false);
  return (
    <>
      <PageHeader
        title={t("nav.support")}
        subtitle={t("support.subtitle")}
        actions={
          tab === "tickets" && (
            <Button onClick={() => setNewTicket(true)}>
              <PlusIcon className="h-4 w-4" /> {t("support.newTicket")}
            </Button>
          )
        }
      />
      <FilterChips
        value={tab}
        onChange={(v) => setParams(v === "tickets" ? {} : { tab: v }, { replace: true })}
        options={[
          { value: "tickets", label: t("support.tabs.tickets") },
          { value: "sessions", label: t("support.tabs.sessions") },
        ]}
      />
      {tab === "tickets" ? <TicketList onNew={() => setNewTicket(true)} /> : <Sessions />}
      <NewTicketSheet open={newTicket} onClose={() => setNewTicket(false)} />
    </>
  );
}

function TicketList({ onNew }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ["tickets"], queryFn: () => apiClient.get("/support/tickets").then((r) => r.data) });
  if (isLoading) return <ListSkeleton rows={3} />;
  if (isError) return <ErrorState onRetry={refetch} />;
  if (!data.length) return <EmptyState title={t("support.none")} description={t("support.noneHint")} action={<Button onClick={onNew}>{t("support.newTicket")}</Button>} />;
  return (
    <ul className="card divide-y divide-zinc-100 overflow-hidden">
      {data.map((ticket) => (
        <li key={ticket.id}>
          <button type="button" onClick={() => navigate(`/support/tickets/${ticket.id}`)} className="flex w-full items-center gap-4 px-4 py-3.5 text-left transition-colors duration-150 hover:bg-zinc-50">
            <span className="w-14 shrink-0 text-sm tabular-nums text-zinc-400">#{ticket.number}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium text-zinc-900">{ticket.subject}</span>
              <span className="block text-xs text-zinc-500">
                {t(`support.categories.${ticket.category}`)} · {formatDateTime(ticket.last_message_at)}
                {ticket.last_from_platform && ticket.status === "waiting" && <span className="ml-1.5 font-medium text-amber-700">· {t("support.yourTurn")}</span>}
              </span>
            </span>
            <TicketStatus status={ticket.status} />
          </button>
        </li>
      ))}
    </ul>
  );
}

function NewTicketSheet({ open, onClose }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ subject: "", category: "question", urgency: "normal", body: "" });
  const set = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));
  const create = useMutation({
    mutationFn: () => apiClient.post("/support/tickets", form).then((r) => r.data),
    onSuccess: (ticket) => {
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      toast.success(t("support.created", { number: ticket.number }));
      setForm({ subject: "", category: "question", urgency: "normal", body: "" });
      onClose();
      navigate(`/support/tickets/${ticket.id}`);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t("support.newTicket")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="ticket-form" disabled={create.isPending || form.subject.trim().length < 3 || form.body.trim().length < 5}>
            {create.isPending ? t("common.sending") : t("support.send")}
          </Button>
        </div>
      }
    >
      <form
        id="ticket-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <p className="text-sm text-zinc-500">{t("support.newHint")}</p>
        <Field label={t("support.subject")}>
          <input className="input" required minLength={3} maxLength={200} value={form.subject} onChange={set("subject")} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("support.category")}>
            <select className="input" value={form.category} onChange={set("category")}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {t(`support.categories.${c}`)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("support.urgency")}>
            <select className="input" value={form.urgency} onChange={set("urgency")}>
              {URGENCIES.map((u) => (
                <option key={u} value={u}>
                  {t(`support.urgencies.${u}`)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Field label={t("support.details")} hint={t("support.detailsHint")}>
          <textarea className="input min-h-[9rem]" required minLength={5} maxLength={10000} value={form.body} onChange={set("body")} />
        </Field>
      </form>
    </Sheet>
  );
}

/** One ticket: the conversation with YGT's team. */
export function TicketPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ["ticket", id], queryFn: () => apiClient.get(`/support/tickets/${id}`).then((r) => r.data) });
  const update = (next) => {
    queryClient.setQueryData(["ticket", id], next);
    queryClient.invalidateQueries({ queryKey: ["tickets"] });
  };
  const reply = useMutation({
    mutationFn: () => apiClient.post(`/support/tickets/${id}/messages`, { body }).then((r) => r.data),
    onSuccess: (next) => {
      update(next);
      setBody("");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const close = useMutation({
    mutationFn: () => apiClient.post(`/support/tickets/${id}/close`).then((r) => r.data),
    onSuccess: (next) => {
      update(next);
      toast.success(t("support.closed"));
    },
  });
  if (isLoading) return <ListSkeleton rows={3} />;
  if (isError) return <ErrorState onRetry={refetch} />;
  const closed = data.status === "closed";
  return (
    <div className="max-w-3xl space-y-5">
      <PageHeader
        eyebrow={<BackLink to="/support">{t("nav.support")}</BackLink>}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {data.subject} <TicketStatus status={data.status} />
          </span>
        }
        subtitle={`#${data.number} · ${t(`support.categories.${data.category}`)} · ${t("support.opened", { date: formatDate(data.created_at) })}`}
        actions={
          !closed && (
            <Button variant="secondary" onClick={() => close.mutate()} disabled={close.isPending}>
              {t("support.close")}
            </Button>
          )
        }
      />
      {data.priority_plan && <p className="-mt-2 text-sm font-medium text-indigo-700">{t("support.priority")}</p>}
      <ol className="space-y-3">
        {data.messages.map((m) => (
          <li key={m.id} className={`flex ${m.from_platform ? "justify-start" : "justify-end"}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-3 ${m.from_platform ? "bg-white ring-1 ring-zinc-200" : "bg-indigo-600 text-white"}`}>
              <p className={`mb-1 text-xs ${m.from_platform ? "text-zinc-500" : "text-indigo-100"}`}>
                <span className="font-medium">{m.from_platform ? t("support.team") : m.author_name}</span> · {formatDateTime(m.created_at)}
              </p>
              <p className="whitespace-pre-line text-[15px] leading-relaxed">{m.body}</p>
            </div>
          </li>
        ))}
      </ol>
      {closed ? (
        <p className="rounded-xl bg-zinc-50 px-4 py-3 text-sm text-zinc-600 ring-1 ring-inset ring-zinc-200">{t("support.closedHint")}</p>
      ) : (
        <form
          className="card space-y-3 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (body.trim()) reply.mutate();
          }}
        >
          <textarea className="input min-h-[6rem]" placeholder={t("support.replyPlaceholder")} value={body} onChange={(e) => setBody(e.target.value)} maxLength={10000} />
          <div className="flex justify-end">
            <Button type="submit" disabled={!body.trim() || reply.isPending}>
              {reply.isPending ? t("common.sending") : t("support.reply")}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- sessions

function Sessions() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { data: slots, isLoading } = useQuery({ queryKey: ["slots"], queryFn: () => apiClient.get("/bookings/slots").then((r) => r.data) });
  const { data: bookings = [] } = useQuery({ queryKey: ["bookings"], queryFn: () => apiClient.get("/bookings").then((r) => r.data) });
  const [day, setDay] = useState(null);
  const [slot, setSlot] = useState(null);
  const [topic, setTopic] = useState("onboarding");
  const [notes, setNotes] = useState("");
  const days = slots?.days ?? [];
  const chosenDay = days.find((d) => d.date === day) ?? days[0];
  const upcoming = bookings.filter((b) => b.status === "booked" && new Date(b.ends_at) > new Date());
  const time = useMemo(() => new Intl.DateTimeFormat(i18n.language, { hour: "2-digit", minute: "2-digit" }), [i18n.language]);
  const dayLabel = useMemo(() => new Intl.DateTimeFormat(i18n.language, { weekday: "short", day: "numeric", month: "short" }), [i18n.language]);
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["slots"] });
    queryClient.invalidateQueries({ queryKey: ["bookings"] });
  };
  const book = useMutation({
    mutationFn: () => apiClient.post("/bookings", { starts_at: slot, topic, notes }).then((r) => r.data),
    onSuccess: (_, __, ctx) => {
      refresh();
      setSlot(null);
      setNotes("");
      toast.success(t("sessions.booked"), { description: t("sessions.bookedHint") });
      celebrate(document.querySelector("[data-booking-confirm]"));
    },
    onError: (error) => {
      toast.error(errorMessage(error));
      refresh();
      setSlot(null);
    },
  });
  const cancel = useMutation({
    mutationFn: (id) => apiClient.post(`/bookings/${id}/cancel`).then((r) => r.data),
    onSuccess: () => {
      refresh();
      toast.success(t("sessions.cancelled"));
    },
  });

  return (
    <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <section className="card min-w-0 space-y-5 p-4 sm:p-6">
        <div>
          <h2 className="text-base font-semibold text-zinc-900">{t("sessions.title")}</h2>
          <p className="mt-0.5 text-sm text-zinc-500">{t("sessions.intro")}</p>
        </div>
        {isLoading ? (
          <ListSkeleton rows={2} />
        ) : !days.length ? (
          <p className="rounded-xl bg-zinc-50 px-4 py-3 text-sm text-zinc-600">{t("sessions.noSlots")}</p>
        ) : (
          <>
            <div>
              <p className="label">{t("sessions.pickDay")}</p>
              <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
                {days.map((d) => (
                  <button
                    key={d.date}
                    type="button"
                    onClick={() => {
                      setDay(d.date);
                      setSlot(null);
                    }}
                    aria-pressed={chosenDay?.date === d.date}
                    className={`shrink-0 rounded-xl px-3 py-2 text-sm font-medium ring-1 ring-inset transition-colors duration-150 ${
                      chosenDay?.date === d.date ? "bg-zinc-900 text-white ring-zinc-900" : "bg-white text-zinc-700 ring-zinc-200 hover:bg-zinc-50"
                    }`}
                  >
                    {dayLabel.format(new Date(`${d.date}T12:00:00`))}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <p className="label">{t("sessions.pickTime", { tz: slots.timezone, minutes: slots.slot_minutes })}</p>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                {chosenDay?.slots.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSlot(s)}
                    aria-pressed={slot === s}
                    className={`rounded-lg py-2 text-sm font-medium tabular-nums ring-1 ring-inset transition-colors duration-150 ${
                      slot === s ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-zinc-700 ring-zinc-200 hover:bg-indigo-50"
                    }`}
                  >
                    {time.format(new Date(s))}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("sessions.topic")}>
                <select className="input" value={topic} onChange={(e) => setTopic(e.target.value)}>
                  {TOPICS.map((v) => (
                    <option key={v} value={v}>
                      {t(`sessions.topics.${v}`)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t("sessions.notes")}>
                <input className="input" maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder={t("sessions.notesPlaceholder")} />
              </Field>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 pt-4" data-booking-confirm>
              <p className="text-sm text-zinc-600">
                {slot ? t("sessions.chosen", { when: `${dayLabel.format(new Date(slot))}, ${time.format(new Date(slot))}` }) : t("sessions.chooseFirst")}
              </p>
              <Button onClick={() => book.mutate()} disabled={!slot || book.isPending}>
                {book.isPending ? t("common.saving") : t("sessions.book")}
              </Button>
            </div>
          </>
        )}
      </section>

      <section className="card min-w-0 p-4 sm:p-6">
        <h2 className="text-base font-semibold text-zinc-900">{t("sessions.upcoming")}</h2>
        {upcoming.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-500">{t("sessions.noneUpcoming")}</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {upcoming.map((b) => (
              <li key={b.id} className="rounded-xl bg-zinc-50 p-3 ring-1 ring-inset ring-zinc-200/70">
                <p className="font-medium text-zinc-900">
                  {dayLabel.format(new Date(b.starts_at))}, {time.format(new Date(b.starts_at))}
                </p>
                <p className="text-sm text-zinc-600">
                  {t(`sessions.topics.${b.topic}`)} · {b.attendee_name}
                </p>
                <button type="button" onClick={() => cancel.mutate(b.id)} className="mt-1 text-sm font-medium text-rose-600 hover:text-rose-700" disabled={cancel.isPending}>
                  {t("sessions.cancel")}
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-4 text-xs text-zinc-500">{t("sessions.inviteNote")}</p>
        <Link to="/support" className="mt-3 inline-block text-sm font-medium text-indigo-600 hover:text-indigo-700">
          {t("sessions.orTicket")}
        </Link>
      </section>
    </div>
  );
}
