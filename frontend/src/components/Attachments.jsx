// Files on an activity or task: attach several at once, open or remove.
// Before a new activity is saved, the chosen files wait in the form
// (`pending`) and are uploaded right after it's created (uploadPending).
import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { errorMessage } from "../utils/format";

export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
const ACCEPT = ".pdf,.png,.jpg,.jpeg,.gif,.webp,.heic,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.csv,.txt";

export function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** Uploads files to an activity; returns how many failed. */
export async function uploadPending(activityId, files) {
  let failed = 0;
  for (const file of files) {
    const body = new FormData();
    body.append("file", file);
    try {
      await apiClient.post(`/activities/${activityId}/attachments`, body);
    } catch (error) {
      failed += 1;
      toast.error(`${file.name}: ${errorMessage(error)}`);
    }
  }
  return failed;
}

function PaperclipIcon({ className = "h-4 w-4" }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
      <path d="m15.5 9.5-5.6 5.6a3.5 3.5 0 0 1-5-5l6-6a2.3 2.3 0 0 1 3.3 3.3l-6 6a1.2 1.2 0 0 1-1.7-1.7l5.4-5.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function FileRow({ name, size, onOpen, onRemove, busy, t }) {
  return (
    <li className="flex items-center gap-2.5 rounded-lg bg-zinc-50 px-3 py-2 ring-1 ring-inset ring-zinc-200/70">
      <PaperclipIcon className="h-4 w-4 shrink-0 text-zinc-400" />
      {onOpen ? (
        <button type="button" className="min-w-0 flex-1 truncate text-left text-sm font-medium text-indigo-700 hover:underline" onClick={onOpen} title={name}>
          {name}
        </button>
      ) : (
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-800" title={name}>
          {name}
        </span>
      )}
      <span className="shrink-0 text-xs tabular-nums text-zinc-500">{formatBytes(size)}</span>
      {onRemove && (
        <button type="button" className="pressable shrink-0 rounded-md px-2 py-1 text-xs font-medium text-zinc-500 hover:bg-zinc-200/60 hover:text-red-600" disabled={busy} onClick={onRemove}>
          {t("attachments.remove")}
        </button>
      )}
    </li>
  );
}

/**
 * activityId: a saved activity (files load from the server), or null for
 * a new one, with `pending`/`onPending` holding the chosen files.
 */
export default function Attachments({ activityId, canWrite = true, pending = [], onPending }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const input = useRef(null);
  const key = ["attachments", activityId];
  const { data: files = [] } = useQuery({
    queryKey: key,
    queryFn: () => apiClient.get(`/activities/${activityId}/attachments`).then((r) => r.data),
    enabled: Boolean(activityId),
  });
  const upload = useMutation({
    mutationFn: (chosen) => uploadPending(activityId, chosen),
    onSuccess: (failed, chosen) => {
      queryClient.invalidateQueries({ queryKey: key });
      if (failed < chosen.length) toast.success(t("attachments.added", { count: chosen.length - failed }));
    },
  });
  const remove = useMutation({
    mutationFn: (file) => apiClient.delete(`/activities/${activityId}/attachments/${file.id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
    onError: (error) => toast.error(errorMessage(error)),
  });

  async function open(file) {
    try {
      const { data } = await apiClient.get(`/activities/${activityId}/attachments/${file.id}`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch (error) {
      toast.error(errorMessage(error));
    }
  }

  function chosen(list) {
    const ok = [];
    for (const file of list) {
      if (file.size > MAX_ATTACHMENT_BYTES) toast.error(t("attachments.tooBig", { name: file.name }));
      else ok.push(file);
    }
    if (!ok.length) return;
    if (activityId) upload.mutate(ok);
    else onPending?.([...pending, ...ok]);
  }

  const empty = !files.length && !pending.length;
  return (
    <section>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-zinc-700">{t("attachments.title")}</h3>
        {canWrite && (
          <>
            <input
              ref={input}
              type="file"
              multiple
              accept={ACCEPT}
              className="sr-only"
              tabIndex={-1}
              onChange={(e) => {
                const list = [...(e.target.files ?? [])];
                e.target.value = "";
                chosen(list);
              }}
            />
            <button type="button" className="btn btn-secondary !h-9 !px-3 !text-sm" disabled={upload.isPending} onClick={() => input.current?.click()}>
              <PaperclipIcon />
              {upload.isPending ? t("attachments.uploading") : t("attachments.attach")}
            </button>
          </>
        )}
      </div>
      {empty ? (
        <p className="mt-1 text-xs text-zinc-500">{canWrite ? t("attachments.hint") : t("attachments.none")}</p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {files.map((f) => (
            <FileRow key={f.id} name={f.filename} size={f.size} t={t} onOpen={() => open(f)} busy={remove.isPending} onRemove={canWrite ? () => remove.mutate(f) : null} />
          ))}
          {pending.map((f, i) => (
            <FileRow key={`p${i}`} name={f.name} size={f.size} t={t} onRemove={() => onPending?.(pending.filter((_, j) => j !== i))} />
          ))}
        </ul>
      )}
    </section>
  );
}
