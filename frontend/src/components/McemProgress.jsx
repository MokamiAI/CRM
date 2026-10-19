import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { Button, ErrorState, Field } from "./ui";
import { useContacts, useTeam } from "../hooks/useApi";
import { errorMessage, formatDate, formatDateTime, todayISO } from "../utils/format";

const STATUSES = { not_started: "Not started", in_progress: "In progress", confirmed: "Confirmed" };
const CHECKPOINTS = { qualified: "Confirm qualification", proposal: "Start solution validation", negotiation: "Confirm proposal review", won: "Confirm sale and start delivery" };
const NEXT = { lead: "qualified", qualified: "proposal", proposal: "negotiation", negotiation: "won" };
const AFTER = new Set(["delivery", "adoption", "value", "health", "renewal", "expansion"]);
const get = url => apiClient.get(url).then(r => r.data);

export function McemReport() {
  const query = useQuery({ queryKey: ["mcem-report"], queryFn: () => get("/mcem/report") });
  if (!query.data?.opportunities.length) return null;
  const data = query.data;
  return <details className="mb-5 rounded-xl border border-zinc-200 bg-white p-4"><summary className="cursor-pointer text-sm font-medium text-zinc-900">Customer progress attention · {data.overdue_milestones} overdue milestones · {data.reviews_due} reviews due · {data.renewals_due} renewals due</summary>
    <ul className="mt-3 divide-y divide-zinc-100">{data.opportunities.map(row => <li key={row.id} className="flex flex-wrap justify-between gap-2 py-2 text-sm"><Link className="min-w-0 break-words text-indigo-700 underline" to={`/deals/${row.id}`}>{row.title}</Link><span className="text-zinc-600">{row.stage} · {row.overdue_milestones} overdue · {row.needs_review} for review{row.next_review_date ? ` · Review ${formatDate(row.next_review_date)}` : ""}{row.renewal_date ? ` · Renewal ${formatDate(row.renewal_date)}` : ""}</span></li>)}</ul>
  </details>;
}

function TeamSelect({ label, value, onChange, team, disabled }) {
  return <Field label={label}><select className="input" value={value ?? ""} disabled={disabled} onChange={e => onChange(e.target.value || null)}>
    <option value="">Choose an owner</option>{team.filter(u => u.role !== "viewer" && u.is_active !== false).map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
  </select></Field>;
}

export default function McemProgress({ deal, canWrite }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: team = [] } = useTeam();
  const [tab, setTab] = useState("milestones");
  const [showAll, setShowAll] = useState(false);
  const [expanding, setExpanding] = useState(false);
  const [expansion, setExpansion] = useState({ title: "", value: "0" });
  const query = useQuery({ queryKey: ["mcem", deal.id], queryFn: () => get(`/deals/${deal.id}/mcem`) });
  const done = data => {
    queryClient.setQueryData(["mcem", deal.id], data);
    for (const key of [["deal", deal.id], ["deals"], ["timeline"], ["mcem-report"], ["mcem-history", deal.id]]) queryClient.invalidateQueries({ queryKey: key });
  };
  const enable = useMutation({ mutationFn: () => apiClient.post(`/deals/${deal.id}/mcem/enable`).then(r => r.data), onSuccess: done, onError: e => toast.error(errorMessage(e)) });
  const disable = useMutation({
    mutationFn: () => apiClient.post(`/deals/${deal.id}/mcem/disable`).then(r => r.data),
    onSuccess: data => { done(data); toast.success("Advanced features turned off. Your progress is saved."); },
    onError: e => toast.error(errorMessage(e)),
  });
  const advance = useMutation({
    mutationFn: stage => apiClient.patch(`/deals/${deal.id}`, { stage }),
    onSuccess: () => {
      for (const key of [["deal", deal.id], ["deals"], ["mcem", deal.id], ["mcem-report"], ["timeline"], ["mcem-history", deal.id]]) queryClient.invalidateQueries({ queryKey: key });
      toast.success("Customer progress updated");
    },
    onError: e => toast.error(errorMessage(e)),
  });
  const createExpansion = useMutation({
    mutationFn: () => apiClient.post(`/deals/${deal.id}/mcem/expansions`, expansion).then(r => r.data),
    onSuccess: data => { queryClient.invalidateQueries({ queryKey: ["deals"] }); navigate(`/deals/${data.id}`); },
    onError: e => toast.error(errorMessage(e)),
  });
  if (query.isLoading) return <section className="card p-5 text-sm text-zinc-500" aria-busy="true">Loading customer progress…</section>;
  if (query.isError) return <ErrorState onRetry={query.refetch} />;
  if (!query.data.enabled) return <section className="card flex flex-wrap items-center justify-between gap-4 p-5">
    <div className="max-w-2xl"><h2 className="text-sm font-semibold text-zinc-900">Customer progress</h2><p className="mt-1 text-sm text-zinc-600">Track customer-confirmed milestones, then continue into delivery and value reviews. Existing work starts unconfirmed; evidence is required before advancing.</p></div>
    {canWrite && <Button variant="secondary" className="font-bold" disabled={enable.isPending} onClick={() => enable.mutate()}>{enable.isPending ? "Enabling…" : "Turn on advanced pipeline"}</Button>}
  </section>;
  const data = query.data;
  const next = NEXT[deal.stage];
  const missing = next ? data.readiness[next] : [];
  const locked = !canWrite || deal.stage === "lost";
  const visible = data.milestones.filter(m => m.applicable && (deal.stage === "won" || !AFTER.has(m.key)));
  const shown = visible.filter(m => showAll || deal.stage === "lost" || m.phase === data.phase || m.needs_review);
  return <section className="card overflow-hidden" aria-label="Customer progress">
    <div className="space-y-3 border-b border-zinc-200 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-semibold text-zinc-900">Customer progress</h2><p className="mt-1 text-sm text-zinc-600">{data.phase}{deal.stage === "lost" ? " · Preserved at loss" : ""}</p></div>
        <span className="text-sm tabular-nums text-zinc-600">{visible.filter(m => m.status === "confirmed").length} of {visible.length} confirmed</span></div>
      {canWrite && <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" className="font-bold" disabled={disable.isPending} onClick={() => disable.mutate()}>
          {disable.isPending ? "Turning off..." : "Turn off advanced features"}
        </Button>
        <p className="text-xs text-zinc-600">Use the standard pipeline. Saved milestones and evidence are kept.</p>
      </div>}
      {data.next_action ? <p className="text-sm text-zinc-700">Next customer action: <Link className="font-medium text-indigo-700 underline" to={`/activities?task=${data.next_action.id}`}>{data.next_action.subject}</Link> · {formatDate(data.next_action.due_date)}</p> : deal.stage !== "won" && deal.stage !== "lost" ? <p className="text-sm text-amber-800">Schedule a customer next action in Next steps below.</p> : null}
      {next && <details className="rounded-lg bg-zinc-50 px-3 py-2 text-sm"><summary className="cursor-pointer font-medium text-zinc-800">{missing.length ? `${missing.length} requirements to ${CHECKPOINTS[next].toLowerCase()}` : `Ready to ${CHECKPOINTS[next].toLowerCase()}`}</summary>{missing.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-zinc-600">{missing.map(s => <li key={s}>{s}</li>)}</ul>}</details>}
      {next && canWrite && <div className="flex flex-wrap items-center gap-3"><Button variant="secondary" disabled={missing.length > 0 || advance.isPending} onClick={() => advance.mutate(next)}>{advance.isPending ? "Updating..." : CHECKPOINTS[next]}</Button><span className="text-xs text-zinc-600">Complete the evidence and handover requirements above to continue.</span></div>}
      <div className="flex flex-wrap gap-1" role="group" aria-label="Customer progress views">{[["milestones", "Milestones"], ["handover", deal.stage === "won" ? "Customer journey" : "Qualification & handover"], ["history", "History"]].map(([value, label]) => <button type="button" key={value} aria-pressed={tab === value} onClick={() => setTab(value)} className={`min-h-11 rounded-lg px-3 text-sm font-medium ${tab === value ? "bg-indigo-50 text-indigo-800" : "text-zinc-600 hover:bg-zinc-50"}`}>{label}</button>)}</div>
    </div>
    {tab === "milestones" && <div><div className="divide-y divide-zinc-100">{shown.map(m => <Milestone key={`${m.id}:${m.updated_at}`} milestone={m} deal={deal} team={team} locked={locked} done={done} />)}</div><button type="button" className="min-h-11 w-full border-t border-zinc-100 px-5 text-left text-sm font-medium text-indigo-700 hover:bg-zinc-50" onClick={() => setShowAll(!showAll)}>{showAll ? "Show current phase" : `Show all milestones (${visible.length})`}</button></div>}
    {tab === "handover" && <div className="space-y-5 p-5">
      <p className="text-sm text-zinc-600">{deal.stage === "won" ? "Delivery and customer success continue here. The original opportunity stays Won and is excluded from the open forecast." : "Prepare the handover before closing the sale. The linked customer journey becomes active when this opportunity is Won."}</p>
      <JourneyForm key={data.journey.updated_at} journey={data.journey} deal={deal} team={team} locked={locked} done={done} />
      {deal.stage === "won" && <div className="space-y-3 border-t border-zinc-200 pt-5"><h3 className="font-semibold text-zinc-900">Expansion opportunities</h3><p className="text-sm text-zinc-600">New needs start as a separate Lead and must qualify through the sales process.</p>
        {data.expansions.map(d => <Link className="block break-words text-sm text-indigo-700 underline" key={d.id} to={`/deals/${d.id}`}>{d.title} · {d.stage}</Link>)}
        {canWrite && !expanding && <Button variant="secondary" onClick={() => setExpanding(true)}>Create expansion opportunity</Button>}
        {expanding && <form className="space-y-3" onSubmit={e => { e.preventDefault(); createExpansion.mutate(); }}><Field label="Expansion opportunity name"><input name="expansion_title" className="input" required minLength={3} maxLength={255} value={expansion.title} onChange={e => setExpansion(p => ({ ...p, title: e.target.value }))} /></Field><Field label="Estimated value"><input className="input" type="number" min="0" step="0.01" value={expansion.value} onChange={e => setExpansion(p => ({ ...p, value: e.target.value }))} /></Field><div className="flex gap-2"><Button type="submit" disabled={createExpansion.isPending}>Create Lead</Button><Button variant="secondary" onClick={() => setExpanding(false)}>Cancel</Button></div></form>}
      </div>}
    </div>}
    {tab === "history" && <McemHistory deal={deal} team={team} milestones={data.milestones} />}
  </section>;
}

function Milestone({ milestone: m, deal, team, locked, done }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ status: m.status, summary: m.summary, owner_id: m.owner_id, due_date: m.due_date ?? "", confirmed_on: m.confirmed_on ?? "" });
  const [evidence, setEvidence] = useState({ source: "", url: "", explanation: "", occurred_on: todayISO(), contact_id: "" });
  const sources = useQuery({ queryKey: ["mcem-sources", deal.id], queryFn: () => get(`/deals/${deal.id}/mcem/sources`), enabled: open });
  const { data: contacts = [] } = useContacts(deal.customer_id);
  const save = useMutation({ mutationFn: () => apiClient.patch(`/deals/${deal.id}/mcem/milestones/${m.key}`, { ...form, due_date: form.due_date || null, confirmed_on: form.confirmed_on || null }).then(r => r.data), onSuccess: data => { done(data); toast.success("Milestone saved"); }, onError: e => toast.error(errorMessage(e)) });
  const add = useMutation({ mutationFn: () => {
    const source = sources.data?.find(s => `${s.kind}:${s.id}` === evidence.source);
    return apiClient.post(`/deals/${deal.id}/mcem/milestones/${m.key}/evidence`, { kind: evidence.source === "link" ? "link" : source?.kind, ref_id: source?.id ?? null, url: evidence.source === "link" ? evidence.url : null, explanation: evidence.explanation, occurred_on: evidence.occurred_on, contact_id: evidence.contact_id || null }).then(r => r.data);
  }, onSuccess: data => { done(data); setEvidence(p => ({ ...p, explanation: "", source: "", url: "" })); toast.success("Customer evidence linked"); }, onError: e => toast.error(errorMessage(e)) });
  const field = key => e => setForm(p => ({ ...p, [key]: e.target.value }));
  return <details data-milestone={m.key} className="group p-4 sm:px-5" onToggle={e => setOpen(e.currentTarget.open)}>
    <summary className="cursor-pointer"><span className="inline-flex w-[calc(100%-1.5rem)] flex-wrap items-center justify-between gap-2 align-middle"><span className="min-w-0"><span className="block text-sm font-medium text-zinc-900">{m.label}</span><span className="mt-0.5 block text-xs text-zinc-500">{m.phase}{m.due_date ? ` · Due ${formatDate(m.due_date)}` : ""}</span></span><span className={`rounded-full px-2 py-1 text-xs font-medium ${m.needs_review ? "bg-amber-50 text-amber-800" : m.status === "confirmed" ? "bg-emerald-50 text-emerald-800" : "bg-zinc-100 text-zinc-700"}`}>{m.needs_review ? "Review required" : STATUSES[m.status]}</span></span></summary>
    {open && <div className="mt-4 space-y-5">
      <form className="space-y-3" onSubmit={e => { e.preventDefault(); save.mutate(); }}>
        <div className="grid gap-3 sm:grid-cols-2"><Field label="Milestone status"><select name="status" className="input" disabled={locked} value={form.status} onChange={field("status")}>{Object.entries(STATUSES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field><TeamSelect label="Milestone owner" value={form.owner_id} team={team} disabled={locked} onChange={owner_id => setForm(p => ({ ...p, owner_id }))} /></div>
        <Field label={m.key === "value" ? "Measured results and actions for any gaps" : "Milestone notes"}><textarea className="input" rows={3} maxLength={5000} disabled={locked} value={form.summary} onChange={field("summary")} /></Field>
        <div className="grid gap-3 sm:grid-cols-2"><Field label="Milestone due date"><input className="input" type="date" disabled={locked} value={form.due_date} onChange={field("due_date")} /></Field><Field label="Customer confirmation date"><input name="confirmed_on" className="input" type="date" max={todayISO()} disabled={locked} value={form.confirmed_on} onChange={field("confirmed_on")} /></Field></div>
        <p className="text-xs text-zinc-500">Confirmed means dated customer evidence supports completion. Sending a quote or completing an internal task does not confirm it.</p>
        {!locked && <Button type="submit" variant="secondary" disabled={save.isPending}>Save milestone</Button>}
      </form>
      <div className="space-y-2 border-t border-zinc-200 pt-4"><h3 className="text-sm font-semibold text-zinc-900">Customer evidence</h3>
        {!m.evidence.length && <p className="text-sm text-zinc-500">No customer evidence linked yet.</p>}
        {m.evidence.map(item => { const source = sources.data?.find(s => s.kind === item.kind && s.id === item.ref_id); return <div className="border-b border-zinc-100 py-2" key={item.id}><p className="whitespace-pre-line break-words text-sm text-zinc-800">{item.explanation}</p><p className="mt-1 break-words text-xs text-zinc-500">{formatDate(item.occurred_on)} · {item.kind} · {item.source_label}</p>{item.url ? <a className="text-sm text-indigo-700 underline" href={item.url} target="_blank" rel="noopener noreferrer">Open agreed document</a> : source ? <Link className="text-sm text-indigo-700 underline" to={source.url}>Open supporting record</Link> : <p className="text-xs text-zinc-500">Source is unavailable; its dated explanation is preserved.</p>}</div>; })}
      </div>
      {!locked && <form className="space-y-3 rounded-lg bg-zinc-50 p-3" onSubmit={e => { e.preventDefault(); add.mutate(); }}>
        <Field label="Supporting record"><select name="evidence_source" className="input" required value={evidence.source} onChange={e => setEvidence(p => ({ ...p, source: e.target.value }))}><option value="">Choose existing evidence</option><option value="link">Agreed document link</option>{sources.data?.map(s => <option key={`${s.kind}:${s.id}`} value={`${s.kind}:${s.id}`}>{s.kind} · {s.label}</option>)}</select></Field>
        {sources.isError && <p role="alert" className="text-sm text-red-700">Evidence could not load. <button type="button" className="underline" onClick={() => sources.refetch()}>Try again</button></p>}
        {evidence.source === "link" && <Field label="Document URL"><input className="input" required type="url" maxLength={2000} value={evidence.url} onChange={e => setEvidence(p => ({ ...p, url: e.target.value }))} /></Field>}
        <Field label="What did the customer confirm?"><textarea name="evidence_explanation" className="input" required minLength={5} maxLength={5000} rows={2} value={evidence.explanation} onChange={e => setEvidence(p => ({ ...p, explanation: e.target.value }))} /></Field>
        <div className="grid gap-3 sm:grid-cols-2"><Field label="Evidence date"><input className="input" required type="date" max={todayISO()} value={evidence.occurred_on} onChange={e => setEvidence(p => ({ ...p, occurred_on: e.target.value }))} /></Field><Field label="Customer contact (optional)"><select className="input" value={evidence.contact_id} onChange={e => setEvidence(p => ({ ...p, contact_id: e.target.value }))}><option value="">Not specified</option>{contacts.map(c => <option key={c.id} value={c.id}>{[c.first_name, c.last_name].filter(Boolean).join(" ")}</option>)}</select></Field></div>
        <Button type="submit" variant="secondary" disabled={add.isPending}>Link customer evidence</Button>
      </form>}
    </div>}
  </details>;
}

function JourneyForm({ journey, deal, team, locked, done }) {
  const [form, setForm] = useState(() => Object.fromEntries(["qualification_reason", "decision_process", "assumptions", "scope", "commitments", "dependencies", "risks", "success_measure", "baseline", "target", "actual", "unit", "delivery_owner_id", "account_owner_id", "next_review_date", "recurring", "renewal_date"].map(k => [k, journey[k] ?? ""])));
  const save = useMutation({ mutationFn: () => {
    const payload = { ...form };
    for (const key of ["baseline", "target", "actual", "delivery_owner_id", "account_owner_id", "next_review_date", "renewal_date"]) payload[key] = payload[key] === "" ? null : payload[key];
    return apiClient.patch(`/deals/${deal.id}/mcem/journey`, payload).then(r => r.data);
  }, onSuccess: data => { done(data); toast.success("Customer journey saved"); }, onError: e => toast.error(errorMessage(e)) });
  const change = key => e => setForm(p => ({ ...p, [key]: e.target.value }));
  const text = (key, label) => <Field key={key} label={label}><textarea name={key} className="input" rows={2} maxLength={5000} disabled={locked} value={form[key]} onChange={change(key)} /></Field>;
  return <form className="space-y-5" onSubmit={e => { e.preventDefault(); save.mutate(); }}>
    <fieldset className="space-y-3"><legend className="mb-3 text-sm font-semibold text-zinc-900">Qualification and customer decisions</legend>{text("qualification_reason", "Why does this opportunity qualify?")}{text("decision_process", "Customer decision process")}{text("assumptions", "Unresolved assumptions")}</fieldset>
    <fieldset className="space-y-3 border-t border-zinc-200 pt-4"><legend className="text-sm font-semibold text-zinc-900">Sales handover</legend>{text("scope", "Agreed scope")}{text("commitments", "Commitments and responsibilities")}{text("dependencies", "Dependencies")}{text("risks", "Known risks")}
      <div className="grid gap-3 sm:grid-cols-2"><TeamSelect label="Delivery owner" value={form.delivery_owner_id} team={team} disabled={locked} onChange={value => setForm(p => ({ ...p, delivery_owner_id: value }))} /><TeamSelect label="Account / customer success owner" value={form.account_owner_id} team={team} disabled={locked} onChange={value => setForm(p => ({ ...p, account_owner_id: value }))} /></div>
    </fieldset>
    <fieldset className="space-y-3 border-t border-zinc-200 pt-4"><legend className="text-sm font-semibold text-zinc-900">Success measures and continuing value</legend>{text("success_measure", "Agreed success measure")}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">{[["baseline", "Baseline (if available)"], ["target", "Target"], ["actual", "Measured result"]].map(([key, label]) => <Field key={key} label={label}><input name={key} className="input" type="number" step="0.0001" disabled={locked} value={form[key]} onChange={change(key)} /></Field>)}</div>
      <Field label="Measurement unit"><input name="unit" className="input" maxLength={80} disabled={locked} value={form.unit} onChange={change("unit")} placeholder="e.g. hours per tender" /></Field>
      <Field label={deal.stage === "won" ? "Next customer review date" : "First customer milestone / review date"}><input name="next_review_date" className="input" type="date" disabled={locked} value={form.next_review_date} onChange={change("next_review_date")} /></Field>
      <label className="flex min-h-11 items-center gap-2 text-sm text-zinc-700"><input type="checkbox" disabled={locked} checked={form.recurring} onChange={e => setForm(p => ({ ...p, recurring: e.target.checked }))} />Recurring contract — track renewal readiness</label>
      {form.recurring && <Field label="Renewal decision date"><input className="input" type="date" disabled={locked} value={form.renewal_date} onChange={change("renewal_date")} /></Field>}
    </fieldset>
    <p className="text-xs text-zinc-500">Changing previously recorded scope or success measures returns affected confirmations for review. History and evidence remain available. Reviews and reminders stay within your team.</p>
    {!locked && <Button type="submit" disabled={save.isPending}>Save customer journey</Button>}
  </form>;
}

function EventDetails({ event, team, milestones }) {
  const d = event.detail;
  const label = key => milestones.find(m => m.key === key)?.label ?? key.replaceAll("_", " ");
  const value = (key, input) => input === null || input === "" ? "Not recorded" : key.endsWith("owner_id") ? team.find(u => u.id === input)?.full_name ?? "Former team member" : typeof input === "boolean" ? input ? "Yes" : "No" : String(input);
  if (event.kind === "enabled") return <p className="mt-2 text-sm text-zinc-600">{d.message}</p>;
  if (event.kind === "evidence_added") return <p className="mt-2 whitespace-pre-line break-words text-sm text-zinc-600">{d.evidence.explanation} · {formatDate(d.evidence.occurred_on)}</p>;
  if (event.kind === "confirmation_review_required") return <p className="mt-2 text-sm text-amber-800">{d.reason}: {d.milestones.map(m => label(m.key)).join(", ")}</p>;
  if (event.kind === "milestone_updated") return <p className="mt-2 whitespace-pre-line text-sm text-zinc-600">{STATUSES[d.before.status]} → {STATUSES[d.after.status]}{d.after.summary ? ` · ${d.after.summary}` : ""}{d.after.confirmed_on ? ` · Confirmed ${formatDate(d.after.confirmed_on)}` : ""}</p>;
  if (event.kind === "journey_updated") return <details className="mt-2 text-sm text-zinc-600"><summary className="cursor-pointer">{Object.keys(d).length} handover or value fields changed</summary><dl className="mt-2 space-y-2">{Object.entries(d).map(([key, change]) => <div key={key}><dt className="font-medium capitalize">{key.replaceAll("_", " ").replace(" id", "")}</dt><dd className="whitespace-pre-line break-words">{value(key, change.from)} → {value(key, change.to)}</dd></div>)}</dl></details>;
  if (event.kind === "expansion_created") return <Link className="mt-2 block text-sm text-indigo-700 underline" to={`/deals/${d.deal_id}`}>{d.title}</Link>;
  return null;
}

function McemHistory({ deal, team, milestones }) {
  const query = useInfiniteQuery({ queryKey: ["mcem-history", deal.id], initialPageParam: 0, queryFn: ({ pageParam }) => get(`/deals/${deal.id}/mcem/history?offset=${pageParam}&limit=10`), getNextPageParam: (last, pages) => last.length === 10 ? pages.reduce((n, p) => n + p.length, 0) : undefined });
  const titles = { disabled: "Advanced pipeline turned off", reenabled: "Advanced pipeline turned back on", enabled: "Advanced pipeline turned on", stage_changed: "Sales stage changed", milestone_updated: "Milestone updated", evidence_added: "Customer evidence linked", confirmation_review_required: "Confirmations need review", journey_updated: "Customer journey updated", expansion_created: "Expansion opportunity created" };
  if (query.isLoading) return <p className="p-5 text-sm text-zinc-500">Loading customer progress history…</p>;
  if (query.isError) return <ErrorState onRetry={query.refetch} />;
  return <div className="p-5"><ol className="divide-y divide-zinc-100">{query.data.pages.flat().map(event => <li key={event.id} className="py-3"><p className="text-sm font-medium text-zinc-900">{titles[event.kind] ?? "Customer progress updated"}{event.detail.key ? ` · ${milestones.find(m => m.key === event.detail.key)?.label ?? event.detail.key}` : ""}</p><p className="mt-1 text-xs text-zinc-500">{formatDateTime(event.created_at)} · {team.find(u => u.id === event.actor_id)?.full_name ?? "Recorded by the system"}</p>{event.kind === "stage_changed" && <p className="mt-1 text-sm text-zinc-700">{event.detail.from} → {event.detail.to} · {event.detail.phase}{event.detail.reason ? ` · ${event.detail.reason}` : ""}</p>}<EventDetails event={event} team={team} milestones={milestones} /></li>)}</ol>{query.hasNextPage && <Button variant="secondary" disabled={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>{query.isFetchingNextPage ? "Loading…" : "Load earlier history"}</Button>}</div>;
}
