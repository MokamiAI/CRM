import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { useChannels, useTeam, useTeamMap, useTeamMessages } from "../hooks/useApi";
import Sheet from "./Sheet";
import { Button, Field, ListSkeleton } from "./ui";
import { errorMessage, formatDateTime } from "../utils/format";

// ---------- Each person's colour ----------
// Soft tints so a busy chat stays calm: the colour sits on the avatar, the
// name and a thin line beside the message, never as a loud bubble. No red:
// it reads as an error. Your own messages are YGT blue.
export const CHAT_COLORS = {
  indigo: { avatar: "bg-indigo-100 text-indigo-700", name: "text-indigo-700", line: "border-indigo-300", tint: "bg-indigo-50/70", swatch: "bg-indigo-400" },
  violet: { avatar: "bg-violet-100 text-violet-700", name: "text-violet-700", line: "border-violet-300", tint: "bg-violet-50/70", swatch: "bg-violet-400" },
  teal: { avatar: "bg-teal-100 text-teal-700", name: "text-teal-700", line: "border-teal-300", tint: "bg-teal-50/70", swatch: "bg-teal-400" },
  emerald: { avatar: "bg-emerald-100 text-emerald-700", name: "text-emerald-700", line: "border-emerald-300", tint: "bg-emerald-50/70", swatch: "bg-emerald-400" },
  amber: { avatar: "bg-amber-100 text-amber-800", name: "text-amber-700", line: "border-amber-300", tint: "bg-amber-50/70", swatch: "bg-amber-400" },
  orange: { avatar: "bg-orange-100 text-orange-700", name: "text-orange-700", line: "border-orange-300", tint: "bg-orange-50/70", swatch: "bg-orange-400" },
  fuchsia: { avatar: "bg-fuchsia-100 text-fuchsia-700", name: "text-fuchsia-700", line: "border-fuchsia-300", tint: "bg-fuchsia-50/70", swatch: "bg-fuchsia-400" },
  cyan: { avatar: "bg-cyan-100 text-cyan-800", name: "text-cyan-700", line: "border-cyan-300", tint: "bg-cyan-50/70", swatch: "bg-cyan-400" },
  sky: { avatar: "bg-sky-100 text-sky-700", name: "text-sky-700", line: "border-sky-300", tint: "bg-sky-50/70", swatch: "bg-sky-400" },
  lime: { avatar: "bg-lime-100 text-lime-800", name: "text-lime-700", line: "border-lime-400", tint: "bg-lime-50/70", swatch: "bg-lime-500" },
};
const COLOR_NAMES = Object.keys(CHAT_COLORS);

/** Their chosen colour, or one picked from their id so it never changes. */
export function colorOf(person) {
  if (person?.chat_color && CHAT_COLORS[person.chat_color]) return CHAT_COLORS[person.chat_color];
  let hash = 0;
  for (const ch of String(person?.id ?? "")) hash = Math.imul(hash ^ ch.charCodeAt(0), 0x9e3779b1) >>> 0;
  return CHAT_COLORS[COLOR_NAMES[hash % COLOR_NAMES.length]];
}

function initials(name = "?") {
  const words = name.trim().split(/\s+/);
  return ((words[0]?.[0] ?? "?") + (words[1]?.[0] ?? "")).toUpperCase();
}

function ChatAvatar({ person, size = "h-8 w-8 text-[11px]" }) {
  return (
    <span aria-hidden="true" className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ring-2 ring-white ${size} ${colorOf(person).avatar}`}>
      {initials(person?.full_name)}
    </span>
  );
}

export const REACTIONS = ["👍", "❤️", "😂", "🎉", "🙏", "👀", "✅"];

// ---------- Message text: links and @mentions ----------

const LINK = /(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"]|www\.[^\s<]+[^\s<.,;:!?)\]'"])/g;

function Linked({ text, mine }) {
  return text.split(LINK).map((part, i) =>
    i % 2 === 1 ? (
      <a
        key={i}
        href={part.startsWith("www.") ? `https://${part}` : part}
        target="_blank"
        rel="noopener noreferrer"
        className={`break-all font-medium underline decoration-1 underline-offset-2 ${mine ? "text-white decoration-white/60" : "text-blue-700 decoration-blue-300 hover:decoration-blue-600"}`}
      >
        {part.replace(/^https?:\/\//, "")}
      </a>
    ) : (
      part
    ),
  );
}

/** "@Lerato Dube" becomes a highlighted name when Lerato is on the team. */
function MessageText({ text, team, me, mine }) {
  const names = team.map((p) => p.full_name).filter(Boolean).sort((a, b) => b.length - a.length);
  if (!names.length) return <Linked text={text} mine={mine} />;
  const pattern = new RegExp(`(@(?:${names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")}))`, "g");
  return text.split(pattern).map((part, i) => {
    if (i % 2 === 0) return <Linked key={i} text={part} mine={mine} />;
    const isMe = part.slice(1) === me?.full_name;
    const style = mine ? "bg-white/20 text-white" : isMe ? "bg-amber-100 text-amber-900" : "bg-blue-50 text-blue-700";
    return (
      <span key={i} className={`rounded px-1 py-px font-semibold ${style}`}>
        {part}
      </span>
    );
  });
}

// ---------- Files ----------

function size(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const fileUrl = (messageId, a) => `/team-chat/messages/${messageId}/attachments/${a.id}`;

async function download(messageId, a) {
  try {
    const { data } = await apiClient.get(fileUrl(messageId, a), { responseType: "blob" });
    const url = URL.createObjectURL(data);
    const link = Object.assign(document.createElement("a"), { href: url, download: a.filename });
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    toast.error(errorMessage(error));
  }
}

/** Pictures show in the chat; files are fetched with the sign-in, so a
 *  plain <img src> can't load them. */
function ImagePreview({ messageId, a }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let url;
    let live = true;
    apiClient.get(fileUrl(messageId, a), { responseType: "blob" }).then(({ data }) => {
      url = URL.createObjectURL(data);
      if (live) setSrc(url);
    }).catch(() => {});
    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [messageId, a]);
  return (
    <button type="button" onClick={() => download(messageId, a)} className="block overflow-hidden rounded-lg ring-1 ring-black/5" title={a.filename}>
      {src ? <img src={src} alt={a.filename} className="max-h-48 max-w-[16rem] object-cover" /> : <span className="block h-32 w-48 animate-pulse bg-zinc-100" />}
    </button>
  );
}

function Attachments({ message, mine }) {
  return (
    <div className="mt-1.5 flex flex-wrap gap-2">
      {message.attachments.map((a) =>
        a.content_type.startsWith("image/") && a.content_type !== "image/heic" ? (
          <ImagePreview key={a.id} messageId={message.id} a={a} />
        ) : (
          <button
            key={a.id}
            type="button"
            onClick={() => download(message.id, a)}
            className={`flex max-w-[16rem] items-center gap-2.5 rounded-lg px-3 py-2 text-left ring-1 ${mine ? "bg-white/15 ring-white/25 hover:bg-white/25" : "bg-white ring-zinc-200 hover:ring-zinc-300"}`}
          >
            <FileIcon className={`h-5 w-5 shrink-0 ${mine ? "text-white" : "text-blue-600"}`} />
            <span className="min-w-0">
              <span className={`block truncate text-sm font-medium ${mine ? "text-white" : "text-zinc-800"}`}>{a.filename}</span>
              <span className={`block text-xs ${mine ? "text-white/75" : "text-zinc-500"}`}>{size(a.size)}</span>
            </span>
          </button>
        ),
      )}
    </div>
  );
}

// ---------- Icons ----------

const icon = (d) =>
  function Icon(props) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
        {d}
      </svg>
    );
  };
const FileIcon = icon(<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></>);
const ClipIcon = icon(<path d="m21 11-8.6 8.6a5 5 0 0 1-7-7L14 4a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l8-8" />);
const ReplyIcon = icon(<><path d="M9 14 4 9l5-5" /><path d="M4 9h10a6 6 0 0 1 6 6v4" /></>);
const SmileIcon = icon(<><circle cx="12" cy="12" r="9" /><path d="M8.5 14.5a4.5 4.5 0 0 0 7 0M9 9.5h.01M15 9.5h.01" /></>);
const PenIcon = icon(<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z" />);
const TrashIcon = icon(<><path d="M4 7h16M10 11v6M14 11v6" /><path d="M6 7l1 13h10l1-13M9 7V4h6v3" /></>);
const LockIcon = icon(<><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>);
const HashIcon = icon(<path d="M5 9h14M5 15h14M10 4 8 20M16 4l-2 16" />);
const GearIcon = icon(<><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>);
const CloseIcon = icon(<path d="M6 6l12 12M18 6 6 18" />);

// ---------- One message ----------

function ActionButton({ label, onClick, children, danger }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 ${danger ? "hover:text-rose-600" : "hover:text-zinc-800"}`}
    >
      {children}
    </button>
  );
}

function Message({ message, grouped, people, team, me, isAdmin, onReply, onChanged }) {
  const { t } = useTranslation();
  const author = people.get(message.author_id);
  const mine = message.author_id === me?.id;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.body);
  const [picking, setPicking] = useState(false);
  const color = colorOf(author);

  const react = useMutation({
    mutationFn: (emoji) => apiClient.post(`/team-chat/messages/${message.id}/reactions`, { emoji }),
    onSuccess: onChanged,
    onError: (error) => toast.error(errorMessage(error)),
  });
  const save = useMutation({
    mutationFn: () => apiClient.patch(`/team-chat/messages/${message.id}`, { body: draft }),
    onSuccess: () => {
      setEditing(false);
      onChanged();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: () => apiClient.delete(`/team-chat/messages/${message.id}`),
    onSuccess: onChanged,
    onError: (error) => toast.error(errorMessage(error)),
  });

  const quoted = message.reply_to;
  const quotedBy = quoted && people.get(quoted.author_id);
  const bubble = mine
    ? "rounded-2xl rounded-tr-md bg-blue-600 text-white shadow-xs"
    : `rounded-2xl rounded-tl-md border-l-[3px] ${color.line} ${color.tint} text-zinc-800`;

  return (
    <div id={`m-${message.id}`} className={`group flex gap-2.5 ${mine ? "flex-row-reverse" : ""} ${grouped ? "mt-1" : "mt-4"}`}>
      <div className="w-8 shrink-0">{!grouped && !mine && <ChatAvatar person={author} />}</div>
      <div className={`flex min-w-0 max-w-[85%] flex-col sm:max-w-[75%] ${mine ? "items-end" : "items-start"}`}>
        {!grouped && (
          <p className={`mb-1 flex items-baseline gap-2 px-1 text-[13px] ${mine ? "flex-row-reverse" : ""}`}>
            <span className={`font-semibold ${mine ? "text-zinc-900" : color.name}`}>{mine ? t("messages.you") : author?.full_name ?? "—"}</span>
            {!mine && author?.job_title && <span className="text-[11px] font-medium text-zinc-500">{author.job_title}</span>}
            <span className="text-[11px] text-zinc-400">{formatDateTime(message.created_at, { dateStyle: "medium", timeStyle: "short" })}</span>
          </p>
        )}
        <div className={`relative flex items-start gap-1 ${mine ? "flex-row-reverse" : ""}`}>
          <div className={`min-w-0 px-3.5 py-2 ${bubble}`}>
            {quoted && (
              <button
                type="button"
                onClick={() => document.getElementById(`m-${quoted.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
                className={`mb-1.5 block w-full rounded-md border-l-2 px-2 py-1 text-left text-xs ${mine ? "border-white/60 bg-white/15 text-white/90" : `${colorOf(quotedBy).line} bg-white/70 text-zinc-600`}`}
              >
                <span className="font-semibold">{quotedBy?.full_name ?? "—"}</span>
                <span className="line-clamp-2">{quoted.body || "📎"}</span>
              </button>
            )}
            {editing ? (
              <div className="min-w-[14rem] space-y-2">
                <textarea className="input text-sm text-zinc-800" rows={2} value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
                <div className="flex justify-end gap-2">
                  <Button variant="secondary" onClick={() => setEditing(false)}>
                    {t("common.cancel")}
                  </Button>
                  <Button disabled={!draft.trim() || save.isPending} onClick={() => save.mutate()}>
                    {t("common.save")}
                  </Button>
                </div>
              </div>
            ) : (
              message.body && (
                <p className="whitespace-pre-line break-words text-sm leading-relaxed">
                  <MessageText text={message.body} team={team} me={me} mine={mine} />
                  {message.edited_at && <span className={`ml-1.5 text-[11px] ${mine ? "text-white/70" : "text-zinc-400"}`}>({t("teamChat.edited")})</span>}
                </p>
              )
            )}
            {message.attachments.length > 0 && <Attachments message={message} mine={mine} />}
          </div>

          {/* Actions: on hover with a mouse, always there on a phone. */}
          {!editing && (
            <div className="flex shrink-0 items-center opacity-0 transition-opacity duration-150 focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100">
              <div className="relative">
                <ActionButton label={t("teamChat.react")} onClick={() => setPicking((v) => !v)}>
                  <SmileIcon className="h-4 w-4" />
                </ActionButton>
                {picking && (
                  <div className={`absolute bottom-full z-10 mb-1 flex gap-0.5 rounded-full bg-white p-1 shadow-pop ring-1 ring-zinc-200 ${mine ? "right-0" : "left-0"}`}>
                    {REACTIONS.map((emoji) => (
                      <button
                        key={emoji}
                        type="button"
                        className="rounded-full p-1 text-lg leading-none transition-transform duration-150 hover:scale-125"
                        onClick={() => {
                          setPicking(false);
                          react.mutate(emoji);
                        }}
                      >
                        {emoji}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <ActionButton label={t("teamChat.reply")} onClick={() => onReply(message)}>
                <ReplyIcon className="h-4 w-4" />
              </ActionButton>
              {mine && message.body && (
                <ActionButton label={t("teamChat.edit")} onClick={() => { setDraft(message.body); setEditing(true); }}>
                  <PenIcon className="h-4 w-4" />
                </ActionButton>
              )}
              {(mine || isAdmin) && (
                <ActionButton label={t("teamChat.delete")} danger onClick={() => window.confirm(t("teamChat.deleteConfirm")) && remove.mutate()}>
                  <TrashIcon className="h-4 w-4" />
                </ActionButton>
              )}
            </div>
          )}
        </div>

        {message.reactions.length > 0 && (
          <div className={`mt-1 flex flex-wrap gap-1 ${mine ? "justify-end" : ""}`}>
            {message.reactions.map((r) => {
              const reacted = r.user_ids.includes(me?.id);
              const who = r.user_ids.map((id) => (id === me?.id ? t("messages.you") : people.get(id)?.full_name ?? "—")).join(", ");
              return (
                <button
                  key={r.emoji}
                  type="button"
                  title={who}
                  onClick={() => react.mutate(r.emoji)}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ring-1 transition-colors ${reacted ? "bg-blue-50 text-blue-700 ring-blue-200" : "bg-white text-zinc-600 ring-zinc-200 hover:ring-zinc-300"}`}
                >
                  <span className="text-sm leading-none">{r.emoji}</span>
                  {r.user_ids.length}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------- The composer ----------

const MAX_FILES = 5;
const MAX_BYTES = 10 * 1024 * 1024;

function Composer({ channel, members, me, replyTo, onCancelReply, onSent }) {
  const { t } = useTranslation();
  const [body, setBody] = useState("");
  const [files, setFiles] = useState([]);
  const [mention, setMention] = useState(null); // { query, start }
  const box = useRef(null);
  const picker = useRef(null);
  const people = useMemo(() => members.filter((p) => p.id !== me?.id), [members, me]);
  const suggestions = mention ? people.filter((p) => p.full_name.toLowerCase().includes(mention.query.toLowerCase())).slice(0, 6) : [];

  useEffect(() => {
    if (replyTo) box.current?.focus();
  }, [replyTo]);

  const send = useMutation({
    mutationFn: () => {
      const mention_ids = people.filter((p) => body.includes(`@${p.full_name}`)).map((p) => p.id);
      const url = `/team-chat/channels/${channel.id}/messages`;
      if (!files.length) return apiClient.post(url, { body, reply_to_id: replyTo?.id ?? null, mention_ids });
      const form = new FormData();
      form.append("body", body);
      if (replyTo) form.append("reply_to_id", replyTo.id);
      mention_ids.forEach((id) => form.append("mention_ids", id));
      files.forEach((f) => form.append("files", f));
      return apiClient.post(`${url}/files`, form);
    },
    onSuccess: () => {
      setBody("");
      setFiles([]);
      onSent();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const ready = (body.trim() || files.length) && !send.isPending;
  const submit = () => ready && send.mutate();

  function track(value, caret) {
    setBody(value);
    const before = value.slice(0, caret);
    const match = before.match(/(^|\s)@([^\s@]{0,30})$/);
    setMention(match ? { query: match[2], start: caret - match[2].length - 1 } : null);
  }

  function pick(person) {
    const caret = box.current?.selectionStart ?? body.length;
    const next = `${body.slice(0, mention.start)}@${person.full_name} ${body.slice(caret)}`;
    setBody(next);
    setMention(null);
    requestAnimationFrame(() => {
      const at = mention.start + person.full_name.length + 2;
      box.current?.focus();
      box.current?.setSelectionRange(at, at);
    });
  }

  function addFiles(list) {
    const picked = [...files, ...list];
    if (picked.length > MAX_FILES) toast.error(t("teamChat.tooManyFiles", { count: MAX_FILES }));
    const tooBig = picked.find((f) => f.size > MAX_BYTES);
    if (tooBig) toast.error(t("teamChat.fileTooBig", { name: tooBig.name }));
    setFiles(picked.filter((f) => f.size <= MAX_BYTES).slice(0, MAX_FILES));
  }

  return (
    <footer
      className="border-t border-zinc-100 p-3"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        if (e.dataTransfer.files?.length) addFiles([...e.dataTransfer.files]);
      }}
    >
      {replyTo && (
        <div className="mb-2 flex items-start gap-2 rounded-lg border-l-2 border-blue-400 bg-blue-50/60 px-3 py-1.5 text-xs text-zinc-600">
          <ReplyIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-600" />
          <span className="min-w-0 flex-1">
            <span className="font-semibold text-zinc-800">{t("teamChat.replyingTo", { name: replyTo.authorName })}</span>
            <span className="block truncate">{replyTo.body || "📎"}</span>
          </span>
          <button type="button" onClick={onCancelReply} aria-label={t("common.cancel")} className="rounded p-0.5 hover:bg-white">
            <CloseIcon className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
      {files.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {files.map((f, i) => (
            <span key={`${f.name}-${i}`} className="inline-flex max-w-[14rem] items-center gap-1.5 rounded-full bg-zinc-100 py-1 pl-2.5 pr-1 text-xs text-zinc-700">
              <FileIcon className="h-3.5 w-3.5 shrink-0 text-blue-600" />
              <span className="truncate">{f.name}</span>
              <button type="button" aria-label={t("teamChat.removeFile")} onClick={() => setFiles(files.filter((_, j) => j !== i))} className="rounded-full p-0.5 hover:bg-zinc-200">
                <CloseIcon className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="relative flex items-end gap-2">
        {suggestions.length > 0 && (
          <ul className="absolute bottom-full left-10 z-10 mb-2 w-64 overflow-hidden rounded-xl bg-white py-1 shadow-pop ring-1 ring-zinc-200" role="listbox">
            {suggestions.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    pick(p);
                  }}
                  className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-sm hover:bg-zinc-50"
                >
                  <ChatAvatar person={p} size="h-6 w-6 text-[10px]" />
                  <span className="min-w-0">
                    <span className="block truncate text-zinc-800">{p.full_name}</span>
                    {p.job_title && <span className="block truncate text-[11px] text-zinc-500">{p.job_title}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <input ref={picker} type="file" multiple className="hidden" onChange={(e) => { addFiles([...e.target.files]); e.target.value = ""; }} />
        <button
          type="button"
          onClick={() => picker.current?.click()}
          title={t("teamChat.attach")}
          aria-label={t("teamChat.attach")}
          className="mb-1 rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800"
        >
          <ClipIcon className="h-5 w-5" />
        </button>
        <textarea
          ref={box}
          className="input min-h-[2.75rem] flex-1"
          rows={1}
          value={body}
          onChange={(e) => track(e.target.value, e.target.selectionStart)}
          onKeyDown={(e) => {
            if (suggestions.length && (e.key === "Enter" || e.key === "Tab")) {
              e.preventDefault();
              pick(suggestions[0]);
              return;
            }
            if (e.key === "Escape") setMention(null);
            // Enter sends; Shift+Enter adds a line, as in every chat app.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          onPaste={(e) => {
            const pasted = [...(e.clipboardData?.files ?? [])];
            if (pasted.length) addFiles(pasted);
          }}
          placeholder={t("messages.teamPlaceholder", { channel: channel?.name ?? "" })}
          aria-label={t("messages.message")}
        />
        <Button disabled={!ready} onClick={submit}>
          {t("messages.send")}
        </Button>
      </div>
      <p className="mt-1.5 hidden pl-11 text-[11px] text-zinc-400 sm:block">{t("teamChat.composerHint")}</p>
    </footer>
  );
}

// ---------- The chat ----------

const PANE = "card flex min-h-[28rem] flex-col overflow-hidden lg:h-[calc(100dvh-15rem)]";

export default function TeamChat({ onNewSpace }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const { data: channels = [], isLoading } = useChannels();
  const channelId = params.get("ch") ?? channels[0]?.id;
  const channel = channels.find((c) => c.id === channelId);
  const { data: messages = [] } = useTeamMessages(channel ? channelId : null);
  const people = useTeamMap();
  const { data: team = [] } = useTeam();
  const { user } = useAuth();
  const [replyTo, setReplyTo] = useState(null);
  const [managing, setManaging] = useState(false);
  const bottom = useRef(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages.length, channelId]);
  useEffect(() => setReplyTo(null), [channelId]);

  // A space we were removed from (or that was deleted): back to General.
  useEffect(() => {
    if (!isLoading && channels.length && params.get("ch") && !channel) setParams({ tab: "team" }, { replace: true });
  }, [isLoading, channels, channel, params, setParams]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["team-messages", channelId] });
  const members = channel?.is_private ? team.filter((p) => channel.member_ids.includes(p.id)) : team;
  const open = channels.filter((c) => !c.is_private);
  const spaces = channels.filter((c) => c.is_private);
  const canManage = channel && !channel.is_general && (channel.created_by === user?.id || ["admin", "manager"].includes(user?.role));
  const canWrite = user?.role !== "viewer";

  if (isLoading) return <ListSkeleton rows={3} />;

  const channelButton = (c) => (
    <li key={c.id}>
      <button
        type="button"
        onClick={() => setParams({ tab: "team", ch: c.id })}
        className={`flex w-full items-center gap-2 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors duration-150 ${c.id === channelId ? "bg-blue-50 font-medium text-blue-700" : "text-zinc-600 hover:bg-zinc-50"}`}
      >
        {c.is_private ? <LockIcon className="h-3.5 w-3.5 shrink-0 opacity-70" /> : <HashIcon className="h-3.5 w-3.5 shrink-0 opacity-70" />}
        <span className="truncate">{c.name}</span>
        {c.is_private && <span className="ml-auto text-[11px] text-zinc-400">{c.member_ids.length}</span>}
      </button>
    </li>
  );

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <nav className="card h-fit space-y-3 p-2" aria-label={t("messages.channels")}>
        <div>
          <p className="px-2.5 pb-1 pt-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{t("teamChat.wholeTeam")}</p>
          <ul className="flex gap-1 overflow-x-auto lg:flex-col">{open.map(channelButton)}</ul>
        </div>
        <div>
          <p className="px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{t("teamChat.spaces")}</p>
          {spaces.length > 0 ? (
            <ul className="flex gap-1 overflow-x-auto lg:flex-col">{spaces.map(channelButton)}</ul>
          ) : (
            <p className="px-2.5 text-xs text-zinc-400">{t("teamChat.noSpaces")}</p>
          )}
          {canWrite && (
            <button type="button" onClick={onNewSpace} className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-left text-sm font-medium text-blue-700 hover:bg-blue-50">
              + {t("teamChat.newSpace")}
            </button>
          )}
        </div>
      </nav>

      <section className={PANE}>
        <header className="flex items-center gap-3 border-b border-zinc-100 px-5 py-3">
          <div className="min-w-0 flex-1">
            <h2 className="flex items-center gap-1.5 font-semibold text-zinc-900">
              {channel?.is_private ? <LockIcon className="h-4 w-4 text-zinc-400" /> : <HashIcon className="h-4 w-4 text-zinc-400" />}
              <span className="truncate">{channel?.name}</span>
            </h2>
            <p className="text-xs text-zinc-500">{channel?.is_private ? t("teamChat.spaceHint", { count: members.length }) : t("messages.teamHint")}</p>
          </div>
          {channel?.is_private && (
            <div className="hidden -space-x-1.5 sm:flex" aria-label={members.map((p) => p.full_name).join(", ")}>
              {members.slice(0, 5).map((p) => (
                <ChatAvatar key={p.id} person={p} size="h-7 w-7 text-[10px]" />
              ))}
              {members.length > 5 && <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-zinc-100 text-[10px] font-semibold text-zinc-600 ring-2 ring-white">+{members.length - 5}</span>}
            </div>
          )}
          {canManage && (
            <button type="button" onClick={() => setManaging(true)} title={t("teamChat.manage")} aria-label={t("teamChat.manage")} className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800">
              <GearIcon className="h-4 w-4" />
            </button>
          )}
        </header>
        <div className="min-h-[16rem] flex-1 overflow-y-auto px-4 pb-4 pt-1 sm:px-5" aria-live="polite">
          {messages.length === 0 && <p className="py-10 text-center text-sm text-zinc-500">{t("messages.teamEmpty")}</p>}
          {messages.map((m, i) => {
            const prev = messages[i - 1];
            const grouped = prev && prev.author_id === m.author_id && new Date(m.created_at) - new Date(prev.created_at) < 5 * 60_000;
            return (
              <Message
                key={m.id}
                message={m}
                grouped={grouped}
                people={people}
                team={team}
                me={user}
                isAdmin={user?.role === "admin"}
                onReply={(msg) => setReplyTo({ id: msg.id, body: msg.body, authorName: people.get(msg.author_id)?.full_name ?? "—" })}
                onChanged={refresh}
              />
            );
          })}
          <div ref={bottom} />
        </div>
        {channel && <Composer channel={channel} members={members} me={user} replyTo={replyTo} onCancelReply={() => setReplyTo(null)} onSent={() => { setReplyTo(null); refresh(); }} />}
      </section>
      <SpaceSheet open={managing} onClose={() => setManaging(false)} space={channel} />
    </div>
  );
}

// ---------- Making and changing a space ----------

export function SpaceSheet({ open, onClose, space }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [, setParams] = useSearchParams();
  const { user } = useAuth();
  const { data: team = [] } = useTeam();
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState([]);
  const [confirming, setConfirming] = useState(false);
  const others = team.filter((p) => p.id !== user?.id);

  useEffect(() => {
    if (!open) return;
    setName(space?.name ?? "");
    setChosen(space ? space.member_ids.filter((id) => id !== user?.id) : []);
    setConfirming(false);
  }, [open, space, user]);

  const done = (channel) => {
    queryClient.invalidateQueries({ queryKey: ["team-channels"] });
    onClose();
    if (channel) setParams({ tab: "team", ch: channel.id });
  };
  const save = useMutation({
    mutationFn: () =>
      space
        ? apiClient.patch(`/team-chat/channels/${space.id}`, { name, ...(space.is_private ? { member_ids: chosen } : {}) }).then((r) => r.data)
        : apiClient.post("/team-chat/channels", { name, member_ids: chosen }).then((r) => r.data),
    onSuccess: (channel) => {
      toast.success(t(space ? "teamChat.saved" : "teamChat.created"));
      done(channel);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: () => apiClient.delete(`/team-chat/channels/${space.id}`),
    onSuccess: () => {
      toast.success(t("teamChat.deleted"));
      queryClient.invalidateQueries({ queryKey: ["team-channels"] });
      onClose();
      setParams({ tab: "team" });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const toggle = (id) => setChosen((list) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]));
  const all = others.length > 0 && others.every((p) => chosen.includes(p.id));

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t(space ? "teamChat.manage" : "teamChat.newSpace")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="space-form" className="btn btn-primary" disabled={save.isPending || !name.trim()}>
            {t(space ? "common.save" : "teamChat.create")}
          </button>
        </>
      }
    >
      <form
        id="space-form"
        className="space-y-5"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label={t("teamChat.spaceName")}>
          <input className="input" required maxLength={60} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("messages.channelNameHint")} />
        </Field>
        {(!space || space.is_private) && (
          <div>
            <div className="mb-2 flex items-baseline justify-between">
              <p className="label mb-0">{t("teamChat.whoCanSee")}</p>
              {others.length > 1 && (
                <button type="button" className="text-xs font-medium text-blue-700 hover:underline" onClick={() => setChosen(all ? [] : others.map((p) => p.id))}>
                  {t(all ? "teamChat.clearAll" : "teamChat.selectAll")}
                </button>
              )}
            </div>
            <p className="mb-3 text-sm text-zinc-500">{t("teamChat.whoCanSeeHint")}</p>
            <ul className="divide-y divide-zinc-100 rounded-xl ring-1 ring-zinc-200">
              <li className="flex items-center gap-3 px-3 py-2.5 text-sm text-zinc-500">
                <ChatAvatar person={user} />
                <span className="flex-1">{user?.full_name} ({t("messages.you")})</span>
              </li>
              {others.map((p) => (
                <li key={p.id}>
                  <label className="flex cursor-pointer items-center gap-3 px-3 py-2.5 text-sm hover:bg-zinc-50">
                    <ChatAvatar person={p} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-zinc-800">{p.full_name}</span>
                      {p.job_title && <span className="block truncate text-xs text-zinc-500">{p.job_title}</span>}
                    </span>
                    <input type="checkbox" className="h-5 w-5 rounded border-zinc-300 text-blue-600 focus:ring-blue-500" checked={chosen.includes(p.id)} onChange={() => toggle(p.id)} />
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}
      </form>
      {space && !space.is_general && (
        <div className="mt-8 rounded-xl border border-rose-200 p-4">
          <p className="font-medium text-zinc-900">{t("teamChat.deleteSpace")}</p>
          <p className="mt-1 text-sm text-zinc-500">{t("teamChat.deleteSpaceHint")}</p>
          {confirming ? (
            <div className="mt-3 flex gap-2">
              <Button variant="secondary" onClick={() => setConfirming(false)}>
                {t("common.cancel")}
              </Button>
              <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
                {t("teamChat.deleteSpaceConfirm")}
              </Button>
            </div>
          ) : (
            <Button variant="secondary" className="mt-3 text-rose-600" onClick={() => setConfirming(true)}>
              {t("teamChat.deleteSpace")}
            </Button>
          )}
        </div>
      )}
    </Sheet>
  );
}
