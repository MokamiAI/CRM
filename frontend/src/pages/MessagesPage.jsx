import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import {
  useAvailableChannels,
  useChannels,
  useConversation,
  useConversations,
  useCustomers,
  useInboxAddress,
  useTeam,
  useTeamMap,
  useTeamMessages,
} from "../hooks/useApi";
import Sheet from "../components/Sheet";
import { PlanNotice } from "../components/Billing";
import { Avatar, Button, EmptyState, ErrorState, Field, FilterChips, ListSkeleton, PageHeader, PlusIcon } from "../components/ui";
import { errorMessage, formatDateTime, todayISO } from "../utils/format";

// "14:05" today, "8 Oct" otherwise: an inbox scans by recency.
function when(iso) {
  const local = new Date(iso);
  const day = `${local.getFullYear()}-${String(local.getMonth() + 1).padStart(2, "0")}-${String(local.getDate()).padStart(2, "0")}`;
  return day === todayISO()
    ? formatDateTime(iso, { hour: "2-digit", minute: "2-digit" })
    : formatDateTime(iso, { day: "numeric", month: "short" });
}

const CHANNEL_STYLE = {
  email: "bg-sky-50 text-sky-700 ring-sky-200/70",
  whatsapp: "bg-emerald-50 text-emerald-700 ring-emerald-200/70",
  sms: "bg-violet-50 text-violet-700 ring-violet-200/70",
};

function ChannelTag({ channel }) {
  const { t } = useTranslation();
  return (
    <span className={`inline-flex shrink-0 items-center rounded px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide ring-1 ring-inset ${CHANNEL_STYLE[channel] ?? CHANNEL_STYLE.email}`}>
      {t(`messages.channel.${channel ?? "email"}`)}
    </span>
  );
}

// An SMS is 160 plain characters (70 with emoji/accents); longer ones are
// sent as several parts, each billed.
// The profile sheet lives in the app shell; it listens for this.
const openProfile = () => window.dispatchEvent(new CustomEvent("ygt:open-profile"));

function smsParts(text) {
  const unicode = /[^\x00-\x7F]/.test(text);
  const single = unicode ? 70 : 160;
  const multi = unicode ? 67 : 153;
  return text.length <= single ? 1 : Math.ceil(text.length / multi);
}

/**
 * Ids already on screen when a thread (or channel) first loaded. Only
 * messages that arrive after that animate in, so opening a thread never
 * "replays" its history. Resets when you switch to another thread.
 */
function useKnownIds(scope, items) {
  const ref = useRef({ scope: undefined, ids: new Set() });
  if (items && ref.current.scope !== scope) {
    ref.current = { scope, ids: new Set(items.map((m) => m.id)) };
  }
  // Read before marking, so a new arrival renders once as "new".
  const snapshot = new Set(ref.current.ids);
  useEffect(() => {
    if (items && ref.current.scope === scope) for (const m of items) ref.current.ids.add(m.id);
  });
  return snapshot;
}

/** Two speech bubbles, linked: the empty inbox, on brand. */
function ConversationArt() {
  return (
    <svg viewBox="0 0 96 64" className="h-16 w-24" aria-hidden="true">
      <defs>
        <linearGradient id="kopano-art" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8b5cf6" />
          <stop offset="1" stopColor="#4f46e5" />
        </linearGradient>
      </defs>
      <path d="M8 10a6 6 0 0 1 6-6h26a6 6 0 0 1 6 6v14a6 6 0 0 1-6 6H22l-8 7v-7h0a6 6 0 0 1-6-6Z" fill="#eef2ff" stroke="#c7d2fe" />
      <path d="M50 30a6 6 0 0 1 6-6h26a6 6 0 0 1 6 6v14a6 6 0 0 1-6 6h0v7l-8-7H56a6 6 0 0 1-6-6Z" fill="url(#kopano-art)" opacity="0.9" />
      <g fill="none" stroke="url(#kopano-art)" strokeWidth="2.5">
        <circle cx="43" cy="44" r="7" />
        <circle cx="53" cy="44" r="7" />
      </g>
      <path d="M16 15h20M16 21h12" stroke="#a5b4fc" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M58 35h20M58 41h12" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" opacity="0.85" />
    </svg>
  );
}

// Ctrl/Cmd+Enter sends from any message box.
function onSubmitKey(event, send) {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    send();
  }
}

export default function MessagesPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "team" ? "team" : "customers";
  const [sheet, setSheet] = useState(null); // new-conversation | new-channel
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";

  return (
    <>
      <PageHeader
        title={t("nav.messages")}
        subtitle={t("messages.subtitle")}
        actions={
          canWrite && (
            <Button onClick={() => setSheet(tab === "team" ? "new-channel" : "new-conversation")}>
              <PlusIcon className="h-4 w-4" /> {t(tab === "team" ? "messages.newChannel" : "messages.newConversation")}
            </Button>
          )
        }
      />
      <FilterChips
        value={tab}
        onChange={(value) => setParams(value === "team" ? { tab: "team" } : {})}
        options={[
          { value: "customers", label: t("messages.tabCustomers") },
          { value: "team", label: t("messages.tabTeam") },
        ]}
      />
      {tab === "team" && <PlanNotice feature="team_chat" />}
      {tab === "team" ? <TeamChat /> : <CustomerInbox />}
      <NewConversationSheet open={sheet === "new-conversation"} onClose={() => setSheet(null)} />
      <NewChannelSheet open={sheet === "new-channel"} onClose={() => setSheet(null)} />
    </>
  );
}

// ---------- Customer inbox ----------

const PANE = "card flex min-h-0 flex-col overflow-hidden lg:h-[calc(100dvh-15rem)]";

function CustomerInbox() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const selected = params.get("c");
  const [filter, setFilter] = useState("open");
  const query = filter === "mine" ? { status: "open", mine: true } : { status: filter };
  const { data = [], isLoading, isError, refetch } = useConversations(query);
  const { data: inbox } = useInboxAddress();
  const select = (id) => setParams(id ? { c: id } : {});

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]">
      <section className={`${PANE} ${selected ? "hidden lg:flex" : ""}`}>
        <div className="border-b border-zinc-100 px-3 pt-3">
          <FilterChips
            value={filter}
            onChange={setFilter}
            options={["open", "mine", "closed"].map((v) => ({ value: v, label: t(`messages.filter.${v}`) }))}
          />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {isLoading ? (
            <ListSkeleton rows={4} />
          ) : isError ? (
            <ErrorState onRetry={refetch} />
          ) : data.length === 0 ? (
            <p className="px-5 py-8 text-center text-sm text-zinc-500">{t(`messages.empty.${filter}`)}</p>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {data.map((c) => {
                const who = c.customer_name ?? c.contact_name ?? c.contact_email ?? (c.contact_phone && `+${c.contact_phone}`);
                const active = c.id === selected;
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => select(c.id)}
                      aria-current={active || undefined}
                      className={`flex w-full gap-3 px-4 py-3 text-left transition-colors duration-150 ${active ? "bg-indigo-50/70" : "hover:bg-zinc-50"}`}
                    >
                      <Avatar name={who} size="sm" />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline justify-between gap-2">
                          <p className={`truncate text-sm ${c.unread ? "font-semibold text-zinc-900" : "font-medium text-zinc-800"}`}>{who}</p>
                          <span className="shrink-0 text-[11px] tabular-nums text-zinc-400">{when(c.last_message_at)}</span>
                        </div>
                        <p className={`flex items-center gap-1.5 truncate text-[13px] ${c.unread ? "font-medium text-zinc-800" : "text-zinc-600"}`}>
                          <ChannelTag channel={c.channel} />
                          <span className="truncate">{c.subject}</span>
                        </p>
                        <p className="truncate text-xs text-zinc-400">{c.last_message_preview}</p>
                      </div>
                      {c.unread && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-indigo-500" aria-label={t("messages.unread")} />}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        {inbox?.address && (
          <p className="border-t border-zinc-100 px-4 py-2.5 text-[11px] leading-snug text-zinc-500">
            {t("messages.inboxHint")}{" "}
            <button
              type="button"
              className="break-all font-mono text-zinc-700 underline decoration-dotted underline-offset-2"
              onClick={() => navigator.clipboard?.writeText(inbox.address).then(() => toast.success(t("messages.copied")))}
            >
              {inbox.address}
            </button>
          </p>
        )}
      </section>

      <section className={`${PANE} ${selected ? "" : "hidden lg:flex"}`}>
        {selected ? (
          <Thread id={selected} onBack={() => select(null)} />
        ) : (
          <div className="flex flex-1 items-center justify-center p-8">
            <EmptyState plain art={<ConversationArt />} title={t("messages.pickTitle")} description={t("messages.pickHint")} />
          </div>
        )}
      </section>
    </div>
  );
}

function MessageBubble({ message, authors, contactName, isNew }) {
  const { t } = useTranslation();
  const author = message.author_id ? authors.get(message.author_id)?.full_name : null;
  const time = formatDateTime(message.created_at, { dateStyle: "medium", timeStyle: "short" });

  if (message.direction === "note") {
    return (
      <div className={`rounded-lg bg-amber-50 px-4 py-3 ring-1 ring-inset ring-amber-200/70 ${isNew ? "bubble-in" : ""}`}>
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-amber-700">
          🔒 {t("messages.internalNote")} · {author ?? "—"} · {time}
        </p>
        <p className="whitespace-pre-line text-sm text-zinc-800">{message.body}</p>
      </div>
    );
  }
  const out = message.direction === "out";
  return (
    <div className={`flex ${out ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 ${out ? "rounded-br-md bg-indigo-600 text-white" : "rounded-bl-md bg-zinc-100 text-zinc-900"} ${
          isNew ? `bubble-in ${out ? "bubble-out" : "bubble-from"}` : ""
        }`}
      >
        <p className="whitespace-pre-line text-sm leading-relaxed">{message.body}</p>
        <p className={`mt-1.5 text-[11px] ${out ? "text-indigo-100" : "text-zinc-500"}`}>
          {out ? author ?? "—" : message.from_email ?? contactName} · {time}
          {out && message.status !== "sent" && (
            <span className={message.status === "failed" ? "ml-1 font-semibold text-rose-200" : "ml-1"} title={message.error ?? undefined}>
              · {t(`messages.status.${message.status}`)}
            </span>
          )}
        </p>
      </div>
    </div>
  );
}

function Thread({ id, onBack }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const { data, isLoading, isError, refetch } = useConversation(id);
  const authors = useTeamMap();
  const { data: team = [] } = useTeam();
  const [body, setBody] = useState("");
  const [kind, setKind] = useState("reply");
  const bottom = useRef(null);
  const known = useKnownIds(id, data?.messages);

  // Opening a thread marks it read on the server; refresh the list and badge.
  useEffect(() => {
    if (data) queryClient.invalidateQueries({ queryKey: ["conversations"] });
  }, [data?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [data?.messages?.length]);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["conversation", id] });
    queryClient.invalidateQueries({ queryKey: ["conversations"] });
    queryClient.invalidateQueries({ queryKey: ["timeline"] });
  };
  const send = useMutation({
    mutationFn: () => apiClient.post(`/conversations/${id}/messages`, { body, kind }),
    onSuccess: () => {
      setBody("");
      refresh();
      if (kind === "reply") toast.success(t("messages.sent"));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const update = useMutation({
    mutationFn: (changes) => apiClient.patch(`/conversations/${id}`, changes),
    onSuccess: refresh,
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (isLoading) return <ListSkeleton rows={3} />;
  if (isError) return <ErrorState onRetry={refetch} />;
  const address = data.channel === "email" ? data.contact_email : `+${data.contact_phone}`;
  const who = data.customer_name ?? data.contact_name ?? address;
  const submit = () => body.trim() && !send.isPending && send.mutate();

  return (
    <>
      <header className="flex flex-wrap items-start gap-3 border-b border-zinc-100 px-4 py-3 sm:px-5">
        <button type="button" onClick={onBack} className="text-sm font-medium text-zinc-500 hover:text-zinc-900 lg:hidden" aria-label={t("messages.back")}>
          ‹
        </button>
        {/* Full width on phones so the subject never gets squeezed by the controls. */}
        <div className="min-w-0 flex-1 basis-[calc(100%-2rem)] sm:basis-0">
          <h2 className="truncate font-semibold text-zinc-900">{data.subject}</h2>
          <p className="truncate text-[13px] text-zinc-500">
            {data.customer_id ? (
              <Link to={`/customers/${data.customer_id}`} className="font-medium text-indigo-600 hover:text-indigo-700">
                {who}
              </Link>
            ) : (
              who
            )}{" "}
            · {address} · <ChannelTag channel={data.channel} />
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
              data.status === "open" ? "bg-emerald-50 text-emerald-700 ring-emerald-200/70" : "bg-zinc-100 text-zinc-500 ring-zinc-200"
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${data.status === "open" ? "bg-emerald-500" : "bg-zinc-400"}`} aria-hidden="true" />
            {t(`messages.filter.${data.status}`)}
          </span>
          {canWrite && (
            <>
              <select
                className="input !h-8 !w-auto !py-0 !text-xs"
                aria-label={t("messages.assignee")}
                value={data.assigned_to ?? ""}
                onChange={(e) => update.mutate({ assigned_to: e.target.value || null })}
              >
                <option value="">{t("messages.unassigned")}</option>
                {team.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                  </option>
                ))}
              </select>
              <Button variant="secondary" className="!h-8 !px-2.5 !text-xs" onClick={() => update.mutate({ status: data.status === "open" ? "closed" : "open" })}>
                {t(data.status === "open" ? "messages.close" : "messages.reopen")}
              </Button>
            </>
          )}
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-zinc-50/40 px-4 py-4 sm:px-5" aria-live="polite">
        {data.messages.map((m) => (
          <MessageBubble key={m.id} message={m} authors={authors} contactName={who} isNew={!known.has(m.id)} />
        ))}
        <div ref={bottom} />
      </div>

      {canWrite && (
        <footer className="border-t border-zinc-100 p-3 sm:p-4">
          <div className="mb-2 inline-flex gap-1 rounded-lg bg-zinc-100 p-0.5 text-xs font-medium" role="radiogroup" aria-label={t("messages.composeAs")}>
            {["reply", "note"].map((k) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={kind === k}
                onClick={() => setKind(k)}
                className={`rounded-md px-2.5 py-1 ${kind === k ? (k === "note" ? "bg-amber-100 text-amber-800" : "bg-white text-zinc-900 shadow-xs") : "text-zinc-500"}`}
              >
                {t(k === "reply" ? "messages.replyTab" : "messages.noteTab")}
              </button>
            ))}
          </div>
          <textarea
            className={`input min-h-[5rem] ${kind === "note" ? "!bg-amber-50/60" : ""}`}
            rows={3}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => onSubmitKey(e, submit)}
            placeholder={t(kind === "reply" ? "messages.replyPlaceholder" : "messages.notePlaceholder", { email: address })}
          />
          <div className="mt-2 flex items-center justify-between gap-3">
            <span className="text-[11px] text-zinc-400">
              {kind === "note"
                ? t("messages.noteHint")
                : data.channel === "sms"
                  ? t("messages.smsCount", { count: body.length, parts: smsParts(body) })
                  : data.channel === "whatsapp"
                    ? t("messages.whatsappHint")
                    : (
                      <>
                        {t("messages.replyHint")} ·{" "}
                        <button type="button" className="font-medium text-indigo-600 hover:text-indigo-700" onClick={openProfile}>
                          {t("signature.edit")}
                        </button>
                      </>
                    )}
            </span>
            <Button disabled={!body.trim() || send.isPending} onClick={submit}>
              {send.isPending ? t("common.sending") : t(kind === "reply" ? "messages.send" : "messages.addNote")}
            </Button>
          </div>
        </footer>
      )}
    </>
  );
}

export function NewConversationSheet({ open, onClose, customerId }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [, setParams] = useSearchParams();
  const { data: customers = [] } = useCustomers({ is_active: true });
  const { data: available = { email: true } } = useAvailableChannels();
  const channels = ["email", "whatsapp", "sms"].filter((c) => available[c]);
  const [form, setForm] = useState({ customer_id: "", channel: "email", subject: "", body: "" });
  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) setForm({ customer_id: customerId ?? "", channel: "email", subject: "", body: "" });
  }
  const customer = customers.find((c) => c.id === form.customer_id);
  const isEmail = form.channel === "email";
  const reachable = customer && (isEmail ? customer.email : customer.phone);
  const set = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const start = useMutation({
    mutationFn: () => apiClient.post("/conversations", isEmail ? form : { ...form, subject: "" }).then((r) => r.data),
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["timeline"] });
      toast.success(t("messages.sent"));
      onClose();
      if (!customerId) setParams({ c: conversation.id });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t("messages.newConversation")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="conversation-form" className="btn btn-primary" disabled={start.isPending || (customer && !reachable)}>
            {start.isPending ? t("common.sending") : t("messages.send")}
          </button>
        </>
      }
    >
      <form
        id="conversation-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          start.mutate();
        }}
      >
        <Field label={t("dealForm.customer")}>
          <select className="input" required value={form.customer_id} onChange={set("customer_id")} disabled={Boolean(customerId)}>
            <option value="" disabled>
              {t("dealForm.chooseCustomer")}
            </option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        {channels.length > 1 && (
          <div>
            <span className="label">{t("messages.sendVia")}</span>
            <div className="inline-flex gap-1 rounded-lg bg-zinc-100 p-1" role="radiogroup" aria-label={t("messages.sendVia")}>
              {channels.map((c) => (
                <button
                  key={c}
                  type="button"
                  role="radio"
                  aria-checked={form.channel === c}
                  onClick={() => setForm((prev) => ({ ...prev, channel: c }))}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${form.channel === c ? "bg-white text-zinc-900 shadow-xs" : "text-zinc-500"}`}
                >
                  {t(`messages.channel.${c}`)}
                </button>
              ))}
            </div>
          </div>
        )}
        {customer && (
          <p className={`-mt-2 text-xs ${reachable ? "text-zinc-500" : "text-rose-600"}`}>
            {reachable
              ? t("messages.toAddress", { email: isEmail ? customer.email : customer.phone })
              : t(isEmail ? "messages.noEmail" : "messages.noPhone")}
          </p>
        )}
        {isEmail && (
          <Field label={t("messages.subject")}>
            <input className="input" required maxLength={255} value={form.subject} onChange={set("subject")} />
          </Field>
        )}
        <Field
          label={t("messages.message")}
          hint={
            form.channel === "sms"
              ? t("messages.smsCount", { count: form.body.length, parts: smsParts(form.body) })
              : form.channel === "whatsapp"
                ? t("messages.whatsappHint")
                : t("messages.replyHint")
          }
        >
          <textarea className="input" required rows={7} value={form.body} onChange={set("body")} />
        </Field>
      </form>
    </Sheet>
  );
}

// ---------- Team chat ----------

function TeamChat() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const { data: channels = [], isLoading } = useChannels();
  const channelId = params.get("ch") ?? channels[0]?.id;
  const channel = channels.find((c) => c.id === channelId);
  const { data: messages = [] } = useTeamMessages(channelId);
  const authors = useTeamMap();
  const { user } = useAuth();
  const [body, setBody] = useState("");
  const bottom = useRef(null);
  const known = useKnownIds(channelId, messages);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages.length, channelId]);

  const post = useMutation({
    mutationFn: () => apiClient.post(`/team-chat/channels/${channelId}/messages`, { body }),
    onSuccess: () => {
      setBody("");
      queryClient.invalidateQueries({ queryKey: ["team-messages", channelId] });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const submit = () => body.trim() && !post.isPending && post.mutate();

  if (isLoading) return <ListSkeleton rows={3} />;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[14rem_minmax(0,1fr)]">
      <nav className="card h-fit p-2" aria-label={t("messages.channels")}>
        <p className="px-2 pb-1 pt-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{t("messages.channels")}</p>
        <ul className="flex gap-1 overflow-x-auto lg:flex-col">
          {channels.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => setParams({ tab: "team", ch: c.id })}
                className={`w-full whitespace-nowrap rounded-md px-2.5 py-1.5 text-left text-sm ${c.id === channelId ? "bg-indigo-50 font-medium text-indigo-700" : "text-zinc-600 hover:bg-zinc-50"}`}
              >
                # {c.name}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <section className={PANE}>
        <header className="border-b border-zinc-100 px-5 py-3">
          <h2 className="font-semibold text-zinc-900"># {channel?.name}</h2>
          <p className="text-xs text-zinc-500">{t("messages.teamHint")}</p>
        </header>
        <div className="min-h-[16rem] flex-1 space-y-4 overflow-y-auto px-5 py-4" aria-live="polite">
          {messages.length === 0 && <p className="py-8 text-center text-sm text-zinc-500">{t("messages.teamEmpty")}</p>}
          {messages.map((m) => {
            const name = authors.get(m.author_id)?.full_name ?? "—";
            const mine = m.author_id === user?.id;
            return (
              <div key={m.id} className={`flex gap-3 ${known.has(m.id) ? "" : "bubble-in bubble-from"}`}>
                <Avatar name={name} size="sm" />
                <div className="min-w-0">
                  <p className="text-[13px]">
                    <span className="font-semibold text-zinc-900">{mine ? t("messages.you") : name}</span>{" "}
                    <span className="text-xs text-zinc-400">{formatDateTime(m.created_at, { dateStyle: "medium", timeStyle: "short" })}</span>
                  </p>
                  <p className="whitespace-pre-line break-words text-sm text-zinc-800">{m.body}</p>
                </div>
              </div>
            );
          })}
          <div ref={bottom} />
        </div>
        <footer className="flex items-end gap-2 border-t border-zinc-100 p-3">
          <textarea
            className="input min-h-[2.75rem] flex-1"
            rows={1}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends; Shift+Enter adds a line, as in every chat app.
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={t("messages.teamPlaceholder", { channel: channel?.name ?? "" })}
            aria-label={t("messages.message")}
          />
          <Button disabled={!body.trim() || post.isPending} onClick={submit}>
            {t("messages.send")}
          </Button>
        </footer>
      </section>
    </div>
  );
}

function NewChannelSheet({ open, onClose }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [, setParams] = useSearchParams();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => apiClient.post("/team-chat/channels", { name }).then((r) => r.data),
    onSuccess: (channel) => {
      queryClient.invalidateQueries({ queryKey: ["team-channels"] });
      setName("");
      onClose();
      setParams({ tab: "team", ch: channel.id });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t("messages.newChannel")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="channel-form" className="btn btn-primary" disabled={create.isPending}>
            {t("common.save")}
          </button>
        </>
      }
    >
      <form
        id="channel-form"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field label={t("messages.channelName")}>
          <input className="input" required maxLength={60} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("messages.channelNameHint")} />
        </Field>
      </form>
    </Sheet>
  );
}
