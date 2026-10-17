import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { Button, Field } from "./ui";
import Sheet from "./Sheet";
import { errorMessage } from "../utils/format";

export default function TicketTemplates({ ticket, onChoose }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "ticket-templates"], queryFn: () => apiClient.get("/admin/ticket-templates").then(r => r.data) });
  const [editing, setEditing] = useState(null);
  const [selected, setSelected] = useState("acknowledged");
  const save = useMutation({
    mutationFn: () => apiClient.put("/admin/ticket-templates", editing).then(r => r.data),
    onSuccess: data => { queryClient.setQueryData(["admin", "ticket-templates"], data); setEditing(null); toast.success("Ticket templates saved"); },
    onError: error => toast.error(errorMessage(error)),
  });
  const apply = key => {
    const template = query.data?.find(t => t.key === key);
    if (!template) return;
    const values = { name: (ticket.created_by_name || "there").split(" ")[0], number: String(ticket.number), subject: ticket.subject };
    onChoose(template.body.replace(/\{(name|number|subject)\}/g, (_, key) => values[key]));
  };
  const current = editing?.find(t => t.key === selected);
  return <>
    <div className="flex flex-wrap items-end gap-2">
      <label className="min-w-0 flex-1 text-sm"><span className="label">Reply template</span>
        <select className="input" value="" disabled={!query.data} onChange={e => apply(e.target.value)}>
          <option value="">{query.isError ? "Templates unavailable" : "Choose a template…"}</option>
          {query.data?.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}
        </select>
      </label>
      <Button type="button" variant="secondary" disabled={!query.data} onClick={() => setEditing(query.data.map(t => ({ ...t })))}>Edit templates</Button>
    </div>
    <p className="text-xs text-zinc-500">Choosing a template replaces your draft. Review and edit it before sending. Status changes email the requester automatically.</p>
    <Sheet open={Boolean(editing)} onClose={() => !save.isPending && setEditing(null)} title="Ticket email templates" footer={<>
      <Button variant="secondary" disabled={save.isPending} onClick={() => setEditing(null)}>Cancel</Button>
      <Button disabled={save.isPending || editing?.some(t => !t.body.trim() || !t.name.trim())} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save templates"}</Button>
    </>}>
      <div className="space-y-4">
        <p className="text-sm text-zinc-600">These templates are shared by YGT support. Ticket received and status templates are also used for automatic emails. Use {"{name}"}, {"{number}"} and {"{subject}"} for ticket details.</p>
        <Field label="Template"><select className="input" value={selected} onChange={e => setSelected(e.target.value)}>{editing?.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}</select></Field>
        <Field label="Template name"><input className="input" maxLength={100} value={current?.name ?? ""} onChange={e => setEditing(rows => rows.map(t => t.key === selected ? { ...t, name: e.target.value } : t))} /></Field>
        <Field label="Email and update text"><textarea className="input min-h-[16rem]" maxLength={10000} value={current?.body ?? ""} onChange={e => setEditing(rows => rows.map(t => t.key === selected ? { ...t, body: e.target.value } : t))} /></Field>
      </div>
    </Sheet>
  </>;
}
