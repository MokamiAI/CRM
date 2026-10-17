import { useState } from "react";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { errorMessage } from "../utils/format";

export function TicketFileInput({ files, onChange, disabled }) {
  return (
    <label className="block space-y-2 text-sm">
      <span className="label">Attachments (optional)</span>
      <input type="file" multiple disabled={disabled} className="input" accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,.heic,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.csv,.txt" onChange={(e) => {
        const next = Array.from(e.target.files ?? []);
        if (next.length > 5 || next.some(f => f.size > 10 * 1024 * 1024) || next.reduce((n, f) => n + f.size, 0) > 20 * 1024 * 1024) {
          toast.error("Choose up to 5 files, 10 MB each and 20 MB in total.");
          e.target.value = "";
          onChange([]);
        } else onChange(next);
      }} />
      <span className="block text-xs text-zinc-500">PDFs, images, Office documents, CSV or text. Up to 5 files, 10 MB each; 20 MB total.</span>
      {files.length > 0 && <span className="block break-words text-xs text-zinc-600">{files.map(f => f.name).join(", ")}</span>}
    </label>
  );
}

export default function TicketAttachments({ ticket, admin = false }) {
  const [downloading, setDownloading] = useState(null);
  if (!ticket.attachments?.length) return null;
  const download = async (file) => {
    setDownloading(file.id);
    try {
      const response = await apiClient.get(`/${admin ? "admin" : "support"}/tickets/${ticket.id}/attachments/${file.id}`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = file.filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { toast.error(errorMessage(error)); }
    finally { setDownloading(null); }
  };
  return <section className="card space-y-2 p-4" aria-label="Ticket attachments">
    <h2 className="text-sm font-semibold text-zinc-900">Attachments</h2>
    <ul className="divide-y divide-zinc-100">{ticket.attachments.map(file => <li key={file.id}>
      <button type="button" disabled={downloading !== null} className="flex min-h-11 w-full items-center justify-between gap-3 py-2 text-left text-sm text-indigo-700 hover:underline" onClick={() => download(file)}>
        <span className="min-w-0 break-all">{file.filename}</span><span className="shrink-0 text-xs text-zinc-500">{downloading === file.id ? "Downloading…" : `${Math.max(1, Math.ceil(file.size / 1024))} KB`}</span>
      </button>
    </li>)}</ul>
  </section>;
}
