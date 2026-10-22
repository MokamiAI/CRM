import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import apiClient from "../../services/apiClient";
import { useAdminOverview } from "../../layouts/AdminLayout";
import { Button, ErrorState, ListSkeleton } from "../../components/ui";
import Sheet from "../../components/Sheet";
import TicketAttachments from "../../components/TicketAttachments";
import TicketTemplates from "../../components/TicketTemplates";
import { errorMessage, formatDate, formatDateTime, formatMoney } from "../../utils/format";

// English only: the admin site is for YGT's own team.
const get = (url, params) => apiClient.get(url, { params }).then((r) => r.data);
const rands = (cents) => formatMoney((cents || 0) / 100);
const PLAN = { hustle: "Hustle", grow: "Grow", scale: "Scale", none: "No plan" };
const STATE_TONE = {
  trialing: "bg-indigo-50 text-indigo-700",
  active: "bg-emerald-50 text-emerald-700",
  past_due: "bg-rose-50 text-rose-700",
  cancelled: "bg-amber-50 text-amber-800",
  trial_ended: "bg-zinc-100 text-zinc-600",
  lapsed: "bg-zinc-100 text-zinc-600",
};

function Title({ children, sub, actions }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">{children}</h1>
        {sub && <p className="mt-0.5 text-sm text-zinc-500">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

function Pill({ tone = "bg-zinc-100 text-zinc-600", children }) {
  return <span className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>{children}</span>;
}

function StatePill({ state, plan }) {
  return (
    <Pill tone={STATE_TONE[state]}>
      {PLAN[plan] ?? plan} · {String(state || "").replace("_", " ")}
    </Pill>
  );
}

function Loading({ query, children }) {
  if (query.isLoading) return <ListSkeleton rows={4} />;
  if (query.isError) return <ErrorState onRetry={query.refetch} />;
  return children(query.data);
}

// ---------------------------------------------------------------- overview

export function AdminOverview() {
  const query = useAdminOverview();
  return (
    <>
      <Title sub="Everything across every company, at a glance.">Overview</Title>
      <Loading query={query}>
        {(o) => (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[
                ["Monthly recurring revenue", rands(o.mrr_cents)],
                ["Revenue, last 30 days", rands(o.revenue_30d_cents)],
                ["Companies", o.tenants],
                ["People using YGT", o.users],
              ].map(([label, value]) => (
                <div key={label} className="card p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
                  <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight text-zinc-900">{value}</p>
                </div>
              ))}
            </div>
            <div className="grid gap-3 lg:grid-cols-3">
              <section className="card p-4">
                <h2 className="text-sm font-semibold text-zinc-900">Companies by status</h2>
                <dl className="mt-3 space-y-2 text-sm">
                  {[
                    ["On a free trial", o.states.trialing],
                    ["Paying", o.states.active],
                    ["Payment failed", o.states.past_due],
                    ["Cancelled (still in period)", o.states.cancelled],
                    ["Read-only (no plan)", o.states.locked],
                    ["Suspended", o.suspended],
                    ["New in the last 30 days", o.signups_30d],
                  ].map(([label, value]) => (
                    <div key={label} className="flex justify-between">
                      <dt className="text-zinc-600">{label}</dt>
                      <dd className="font-medium tabular-nums text-zinc-900">{value}</dd>
                    </div>
                  ))}
                </dl>
              </section>
              <section className="card p-4 lg:col-span-2">
                <h2 className="text-sm font-semibold text-zinc-900">Needs attention</h2>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {[
                    ["/admin/tickets", "Open tickets", o.open_tickets, o.priority_tickets ? `${o.priority_tickets} priority` : null],
                    ["/admin/contact", "New contact requests", o.new_contacts],
                    ["/admin/bookings", "Upcoming sessions", o.upcoming_bookings],
                    ["/admin/errors", "Errors in the last 24 hours", o.errors_24h],
                  ].map(([to, label, value, extra]) => (
                    <Link key={to} to={to} className="flex items-center justify-between rounded-xl bg-zinc-50 px-4 py-3 ring-1 ring-inset ring-zinc-200/70 hover:bg-zinc-100">
                      <span className="text-sm text-zinc-700">
                        {label}
                        {extra && <span className="ml-1.5 text-xs font-medium text-indigo-700">({extra})</span>}
                      </span>
                      <span className="text-lg font-semibold tabular-nums text-zinc-900">{value}</span>
                    </Link>
                  ))}
                </div>
              </section>
            </div>
            <YgtDetails />
          </div>
        )}
      </Loading>
    </>
  );
}

const YGT_FIELDS = [
  ["bank_name", "Bank name", ""],
  ["account_holder", "Account holder", ""],
  ["account_number", "Account number", ""],
  ["branch_code", "Branch code", ""],
  ["account_type", "Account type", ""],
  ["legal_name", "Legal name", "YGT (Pty) Ltd"],
  ["registration_number", "Registration number", "2026/123456/07"],
  ["vat_number", "VAT number (leave empty until registered)", ""],
  ["email", "Billing email", "billing@yougt.co.za"],
  ["phone", "Phone", ""],
  ["website", "Website", "yougt.co.za"],
];

/** YGT's own details on subscriber invoices. A VAT number turns new
 *  invoices into tax invoices with VAT; issued ones never change. */
function YgtDetails() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "ygt-details"], queryFn: () => get("/admin/ygt-details") });
  const [form, setForm] = useState(null);
  if (query.data && !form) setForm(query.data);
  const save = useMutation({
    mutationFn: () => apiClient.put("/admin/ygt-details", form).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.setQueryData(["admin", "ygt-details"], data);
      setForm(data);
      toast.success("Saved. New subscriber invoices use these details.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  if (!form) return null;
  return (
    <section className="card p-5">
      <h2 className="text-sm font-semibold text-zinc-900">YGT's details on subscriber invoices</h2>
      <p className="mt-0.5 text-sm text-zinc-500">
        Every subscription payment gets an invoice from these details, emailed to the company. Without a VAT number it's an "Invoice" with no VAT; add the number once
        registered and new invoices become tax invoices. Invoices already issued keep their details.
      </p>
      <form
        className="mt-4 grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        {YGT_FIELDS.map(([key, label, placeholder]) => (
          <label key={key} className="text-sm">
            <span className="mb-1 block font-medium text-zinc-700">{label}</span>
            <input className="input" required={key === "legal_name"} value={form[key] ?? ""} placeholder={placeholder} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
          </label>
        ))}
        <label className="text-sm sm:col-span-2">
          <span className="mb-1 block font-medium text-zinc-700">Address</span>
          <textarea className="input" rows={3} value={form.address ?? ""} onChange={(e) => setForm({ ...form, address: e.target.value })} />
        </label>
        <div className="sm:col-span-2">
          <Button type="submit" disabled={save.isPending}>
            Save details
          </Button>
        </div>
      </form>
    </section>
  );
}

// ---------------------------------------------------------------- tenants

export function AdminTenants() {
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ["admin", "tenants", search], queryFn: () => get("/admin/tenants", search ? { search } : undefined) });
  return (
    <>
      <Title sub="Every company on YGT, with what they use and pay.">Tenants</Title>
      <input type="search" className="input mb-4 max-w-sm" placeholder="Search by company or email…" value={search} onChange={(e) => setSearch(e.target.value)} />
      <Loading query={query}>
        {(rows) => (
          <div className="card overflow-x-auto">
            <table className="w-full min-w-[56rem] text-sm">
              <thead className="table-head">
                <tr>
                  <th>Company</th>
                  <th>Plan</th>
                  <th className="text-right">People</th>
                  <th className="text-right">Clients</th>
                  <th className="text-right">Invoices</th>
                  <th className="text-right">Invoiced</th>
                  <th className="text-right">MRR</th>
                  <th>Last active</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.id} className="table-row" onClick={() => navigate(`/admin/tenants/${t.id}`)}>
                    <td>
                      <p className="font-medium text-zinc-900">
                        {t.name} {t.suspended && <Pill tone="bg-rose-100 text-rose-700">Suspended</Pill>}
                      </p>
                      <p className="text-xs text-zinc-500">
                        {t.owner_email} · since {formatDate(t.created_at)}
                      </p>
                    </td>
                    <td>
                      <StatePill state={t.state} plan={t.plan} />
                    </td>
                    <td className="text-right tabular-nums">{t.users}</td>
                    <td className="text-right tabular-nums">{t.customers}</td>
                    <td className="text-right tabular-nums">{t.invoices}</td>
                    <td className="text-right tabular-nums">{formatMoney(t.invoiced)}</td>
                    <td className="text-right tabular-nums">{rands(t.mrr_cents)}</td>
                    <td className="whitespace-nowrap text-zinc-500">{t.last_active_at ? formatDateTime(t.last_active_at) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loading>
    </>
  );
}

export function AdminTenant() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "tenant", id], queryFn: () => get(`/admin/tenants/${id}`) });
  const activity = useQuery({ queryKey: ["admin", "activity", id], queryFn: () => get("/admin/activity", { company_id: id, limit: 30 }) });
  const errors = useQuery({ queryKey: ["admin", "errors", id], queryFn: () => get("/admin/errors", { company_id: id, limit: 20 }) });
  const tickets = useQuery({ queryKey: ["admin", "tickets", id], queryFn: () => get("/admin/tickets", { company_id: id }) });
  const [refundOf, setRefundOf] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const done = (data) => {
    queryClient.setQueryData(["admin", "tenant", id], data);
    queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "overview"] });
  };
  const act = useMutation({
    mutationFn: ({ path, body }) => apiClient.post(`/admin/tenants/${id}/${path}`, body).then((r) => r.data),
    onSuccess: (data, vars) => {
      done(data);
      toast.success(vars.message);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const confirmPayment = useMutation({
    mutationFn: invoiceId => apiClient.post(`/admin/subscription-invoices/${invoiceId}/confirm-payment`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["admin"] }); toast.success("Payment recorded and subscription activated"); },
    onError: error => toast.error(errorMessage(error)),
  });
  function suspend() {
    const reason = window.prompt("Why are you suspending this company? (They'll see that their account is suspended and to contact support.)");
    if (reason && reason.trim().length >= 3) act.mutate({ path: "suspend", body: { reason }, message: "Suspended" });
  }
  function extend(paying) {
    const days = Number(window.prompt(
      paying
        ? "Put this company on a free trial for how many days? Their paid plan stops now (a card subscription is cancelled in Paystack); they choose a plan again when the trial ends."
        : "Extend the free trial by how many days?",
      "7",
    ));
    if (days > 0) act.mutate({ path: "extend-trial", body: { days }, message: `Trial extended by ${days} days` });
  }

  return (
    <Loading query={query}>
      {(t) => (
        <>
          <Link to="/admin/tenants" className="text-sm text-zinc-500 hover:text-zinc-900">
            ← Tenants
          </Link>
          <Title
            sub={`${t.owner_email ?? ""} · on YGT since ${formatDate(t.created_at)}`}
            actions={
              <>
                {t.suspended ? (
                  <Button variant="secondary" onClick={() => act.mutate({ path: "unsuspend", message: "Unsuspended" })}>
                    Unsuspend
                  </Button>
                ) : (
                  <Button variant="danger" onClick={suspend}>
                    Suspend
                  </Button>
                )}
                {["active", "past_due"].includes(t.state) ? (
                  <Button variant="secondary" onClick={() => extend(true)}>
                    Put on trial
                  </Button>
                ) : (
                  <Button variant="secondary" onClick={() => extend(false)}>
                    Extend trial
                  </Button>
                )}
                <Button variant="danger" onClick={() => setDeleting(t)}>
                  Delete company
                </Button>
              </>
            }
          >
            <span className="flex flex-wrap items-center gap-3">
              {t.name} <StatePill state={t.state} plan={t.plan} />
            </span>
          </Title>
          {t.suspended && (
            <p className="mb-5 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800 ring-1 ring-inset ring-rose-200">
              Suspended {formatDateTime(t.suspended_at)}: {t.suspended_reason}
            </p>
          )}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            {[
              ["People", t.users],
              ["Clients", t.customers],
              ["Quotes", t.quotes],
              ["Invoices", t.invoices],
              ["Invoiced", formatMoney(t.invoiced)],
              ["Collected", formatMoney(t.collected)],
            ].map(([label, value]) => (
              <div key={label} className="card p-3">
                <p className="text-xs text-zinc-500">{label}</p>
                <p className="font-semibold tabular-nums text-zinc-900">{value}</p>
              </div>
            ))}
          </div>

          <div className="mt-5 grid items-start gap-5 lg:grid-cols-2">
            <section className="card p-4">
              <h2 className="text-sm font-semibold text-zinc-900">Subscription</h2>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                <dt className="text-zinc-500">Plan</dt>
                <dd>
                  {PLAN[t.subscription.plan] ?? "—"} ({t.subscription.interval}, {t.seats} seats)
                </dd>
                <dt className="text-zinc-500">Status</dt>
                <dd>{t.subscription.status}</dd>
                <dt className="text-zinc-500">{t.state === "trialing" ? "Trial ends" : "Period ends"}</dt>
                <dd>{formatDate(t.state === "trialing" ? t.trial_ends_at : t.subscription.current_period_end) || "—"}</dd>
                <dt className="text-zinc-500">Worth per month</dt>
                <dd>{rands(t.mrr_cents)}</dd>
                <dt className="text-zinc-500">Billing email</dt>
                <dd className="truncate">{t.subscription.billing_email ?? "—"}</dd>
                <dt className="text-zinc-500">VAT number</dt>
                <dd>{t.tax_number ?? "—"}</dd>
              </dl>
              {t.subscription_invoices?.some(i => i.manual && !i.is_paid) && <div className="mt-5 space-y-2">
                <h3 className="text-sm font-semibold text-zinc-900">Awaiting bank payment</h3>
                <p className="text-xs text-zinc-600">Confirm only after the full amount has arrived in your bank account.</p>
                {t.subscription_invoices.filter(i => i.manual && !i.is_paid).map(i => <div key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                  <span>{i.number} - {rands(i.amount_cents)}</span>
                  <Button variant="secondary" disabled={confirmPayment.isPending} onClick={() => confirmPayment.mutate(i.id)}>Confirm bank payment received</Button>
                </div>)}
              </div>}
              <h3 className="mt-5 text-sm font-semibold text-zinc-900">Payments</h3>
              {t.payments.length === 0 ? (
                <p className="mt-2 text-sm text-zinc-500">No payments yet.</p>
              ) : (
                <ul className="mt-2 divide-y divide-zinc-100 text-sm">
                  {t.payments.map((p) => (
                    <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                      <span>
                        {p.invoice_number && <span className="mr-1.5 font-medium text-zinc-900">{p.invoice_number}</span>}
                        {formatDate(p.paid_at)} · {PLAN[p.plan]} {p.interval} · <span className="font-medium tabular-nums">{rands(p.amount_cents)}</span>
                        <span className="block text-xs text-zinc-400">Payment ref {p.reference}</span>
                        {p.refunded_cents > 0 && <span className="ml-1.5 text-xs text-rose-700">({rands(p.refunded_cents)} refunded)</span>}
                      </span>
                      {!p.reference.startsWith("manual:") && p.refunded_cents < p.amount_cents && (
                        <button type="button" onClick={() => setRefundOf(p)} className="text-sm font-medium text-rose-600 hover:text-rose-700">
                          Refund…
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="card p-4">
              <h2 className="text-sm font-semibold text-zinc-900">People</h2>
              <ul className="mt-2 divide-y divide-zinc-100 text-sm">
                {t.people.map((p) => (
                  <li key={p.id} className="flex justify-between gap-2 py-2">
                    <span className={p.active ? "" : "text-zinc-400 line-through"}>
                      {p.name} <span className="text-zinc-500">· {p.email}</span>
                    </span>
                    <span className="text-zinc-500">{p.role}</span>
                  </li>
                ))}
              </ul>
              <h3 className="mt-5 text-sm font-semibold text-zinc-900">Tickets</h3>
              <ul className="mt-2 divide-y divide-zinc-100 text-sm">
                {(tickets.data ?? []).map((tk) => (
                  <li key={tk.id} className="py-2">
                    <Link to={`/admin/tickets/${tk.id}`} className="hover:underline">
                      #{tk.number} {tk.subject}
                    </Link>{" "}
                    <span className="text-zinc-500">· {tk.status}</span>
                  </li>
                ))}
                {tickets.data?.length === 0 && <li className="py-2 text-zinc-500">None.</li>}
              </ul>
            </section>
          </div>

          <section className="card mt-5 overflow-x-auto">
            <h2 className="px-4 pt-4 text-sm font-semibold text-zinc-900">Recent activity</h2>
            <ActivityTable rows={activity.data ?? []} showCompany={false} />
          </section>
          <section className="card mt-5 p-4">
            <h2 className="text-sm font-semibold text-zinc-900">Errors</h2>
            <ErrorList rows={errors.data ?? []} />
          </section>
          <RefundSheet payment={refundOf} onClose={() => setRefundOf(null)} onDone={() => queryClient.invalidateQueries({ queryKey: ["admin", "tenant", id] })} />
          <DeleteCompanySheet tenant={deleting} onClose={() => setDeleting(null)} />
        </>
      )}
    </Loading>
  );
}

/** POPIA deletion requests and closed accounts: erases the company and everything it holds. */
function DeleteCompanySheet({ tenant, onClose }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [typed, setTyped] = useState("");
  const remove = useMutation({
    mutationFn: () => apiClient.post(`/admin/tenants/${tenant.id}/delete`, { confirm_name: typed }).then((r) => r.data),
    onSuccess: (r) => {
      toast.success(`${r.deleted} deleted`, { description: `${r.people} people, ${r.customers} clients and ${r.invoices} invoices erased.` });
      queryClient.invalidateQueries({ queryKey: ["admin"] });
      setTyped("");
      onClose();
      navigate("/admin/tenants", { replace: true });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const matches = tenant && typed.trim() === tenant.name.trim();
  return (
    <Sheet
      open={Boolean(tenant)}
      onClose={onClose}
      title="Delete this company"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" onClick={() => remove.mutate()} disabled={!matches || remove.isPending}>
            {remove.isPending ? "Deleting…" : "Delete everything"}
          </Button>
        </div>
      }
    >
      {tenant && (
        <div className="space-y-4 text-sm">
          <p className="text-zinc-600">
            This permanently erases <strong className="text-zinc-900">{tenant.name}</strong>: its people, clients, deals, quotes, invoices, messages, tickets and
            settings. It can't be undone. Their Paystack subscription is cancelled first, so they won't be charged again.
          </p>
          <p className="text-zinc-600">Use this for a POPIA deletion request or a closed account. Export anything they asked for before you delete.</p>
          <label className="block">
            <span className="label">Type the company name to confirm</span>
            <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={tenant.name} autoComplete="off" />
          </label>
        </div>
      )}
    </Sheet>
  );
}

function RefundSheet({ payment, onClose, onDone }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const left = payment ? (payment.amount_cents - payment.refunded_cents) / 100 : 0;
  const refund = useMutation({
    mutationFn: () =>
      apiClient.post(`/admin/payments/${payment.id}/refund`, { amount_cents: amount ? Math.round(Number(amount) * 100) : null, reason }).then((r) => r.data),
    onSuccess: (r) => {
      toast.success(`Refund ${r.status}: ${rands(r.amount_cents)}`);
      setAmount("");
      setReason("");
      onDone();
      onClose();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <Sheet
      open={Boolean(payment)}
      onClose={onClose}
      title="Refund a payment"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" onClick={() => refund.mutate()} disabled={reason.trim().length < 3 || refund.isPending}>
            {refund.isPending ? "Refunding…" : `Refund ${amount ? formatMoney(Number(amount)) : formatMoney(left)}`}
          </Button>
        </div>
      }
    >
      {payment && (
        <div className="space-y-4 text-sm">
          <p className="text-zinc-600">
            {formatDate(payment.paid_at)} · {rands(payment.amount_cents)} · up to {formatMoney(left)} can still be refunded. The money goes back to their card through Paystack,
            usually within 5 to 10 business days.
          </p>
          <label className="block">
            <span className="label">Amount (R), empty for the full {formatMoney(left)}</span>
            <input className="input" type="number" min="0.01" step="0.01" max={left} value={amount} onChange={(e) => setAmount(e.target.value)} />
          </label>
          <label className="block">
            <span className="label">Reason (kept on record)</span>
            <input className="input" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Cancelled within 14 days of a yearly payment" />
          </label>
        </div>
      )}
    </Sheet>
  );
}

// ---------------------------------------------------------------- help desk

const TICKET_FILTERS = [
  ["active", "Needs work"],
  ["waiting", "Waiting on client"],
  ["resolved", "Resolved"],
  ["closed", "Closed"],
  ["", "All"],
];
const STATUSES = ["open", "in_progress", "waiting", "resolved", "closed"];
const TICKET_STATUS_LABELS = { open: "Open", in_progress: "In progress", waiting: "Waiting on client", resolved: "Resolved", closed: "Closed" };

export function AdminTickets() {
  const [status, setStatus] = useState("active");
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ["admin", "tickets", "list", status], queryFn: () => get("/admin/tickets", status ? { status } : undefined), refetchInterval: 30_000 });
  return (
    <>
      <Title sub="Priority support (Scale) first, then whoever has waited longest.">Help desk</Title>
      <div className="mb-4 flex flex-wrap gap-2">
        {TICKET_FILTERS.map(([value, label]) => (
          <button
            key={label}
            type="button"
            onClick={() => setStatus(value)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${status === value ? "bg-zinc-900 text-white" : "bg-white text-zinc-600 ring-1 ring-inset ring-zinc-200"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <Loading query={query}>
        {(rows) =>
          rows.length === 0 ? (
            <p className="card p-6 text-center text-sm text-zinc-500">Nothing here. 🎉</p>
          ) : (
            <ul className="card divide-y divide-zinc-100 overflow-hidden">
              {rows.map((t) => (
                <li key={t.id}>
                  <button type="button" onClick={() => navigate(`/admin/tickets/${t.id}`)} className="flex w-full items-center gap-4 px-4 py-3 text-left hover:bg-zinc-50">
                    <span className="w-14 shrink-0 text-sm tabular-nums text-zinc-400">#{t.number}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-zinc-900">
                        {t.priority_plan && <Pill tone="bg-indigo-600 text-white">Priority</Pill>} {t.urgency === "high" && <Pill tone="bg-rose-100 text-rose-700">Urgent</Pill>}{" "}
                        {t.subject}
                      </span>
                      <span className="block truncate text-xs text-zinc-500">
                        {t.company_name} · {t.created_by_name} · {formatDateTime(t.last_message_at)}
                        {t.assigned_to && ` · ${t.assigned_to}`}
                      </span>
                    </span>
                    <Pill>{TICKET_STATUS_LABELS[t.status] ?? t.status}</Pill>
                  </button>
                </li>
              ))}
            </ul>
          )
        }
      </Loading>
    </>
  );
}

export function AdminTicket() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [internal, setInternal] = useState(false);
  const query = useQuery({ queryKey: ["admin", "ticket", id], queryFn: () => get(`/admin/tickets/${id}`), refetchInterval: 15000 });
  const done = (data) => {
    queryClient.setQueryData(["admin", "ticket", id], data);
    queryClient.invalidateQueries({ queryKey: ["admin", "tickets"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "overview"] });
  };
  const reply = useMutation({
    mutationFn: () => apiClient.post(`/admin/tickets/${id}/messages`, { body, internal }).then((r) => r.data),
    onSuccess: (data) => {
      done(data);
      setBody("");
      toast.success(internal ? "Note added" : "Reply sent");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const update = useMutation({
    mutationFn: (changes) => apiClient.patch(`/admin/tickets/${id}`, changes).then((r) => r.data),
    onSuccess: done,
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <Loading query={query}>
      {(t) => (
        <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="min-w-0">
            <Link to="/admin/tickets" className="text-sm text-zinc-500 hover:text-zinc-900">
              ← Help desk
            </Link>
            <Title sub={`#${t.number} · ${t.company_name} · ${t.created_by_name} (${t.created_by_email})`}>
              <span className="flex flex-wrap items-center gap-2">
                {t.priority_plan && <Pill tone="bg-indigo-600 text-white">Priority</Pill>} {t.subject}
              </span>
            </Title>
            <ol className="space-y-3">
              {t.messages.map((m) => (
                <li key={m.id} className={`flex ${m.from_platform ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                      m.internal ? "bg-amber-50 ring-1 ring-amber-200" : m.from_platform ? "bg-zinc-900 text-white" : "bg-white ring-1 ring-zinc-200"
                    }`}
                  >
                    <p className={`mb-1 text-xs ${m.from_platform && !m.internal ? "text-zinc-400" : "text-zinc-500"}`}>
                      <span className="font-medium">{m.internal ? `Internal note · ${m.author_name}` : m.author_name}</span> · {formatDateTime(m.created_at)}
                    </p>
                    <p className="whitespace-pre-line text-[15px] leading-relaxed">{m.body}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-4"><TicketAttachments ticket={t} admin /></div>
            <form
              className={`card mt-4 space-y-3 p-4 ${internal ? "ring-2 ring-amber-300" : ""}`}
              onSubmit={(e) => {
                e.preventDefault();
                if (body.trim()) reply.mutate();
              }}
            >
              {!internal && <TicketTemplates ticket={t} onChoose={setBody} />}
              <textarea aria-label={internal ? "Internal note" : "Reply text"} maxLength={10000} className="input min-h-[7rem]" placeholder={internal ? "A note for YGT's team (they won't see it)…" : `Reply to ${t.created_by_name ?? "them"}…`} value={body} onChange={(e) => setBody(e.target.value)} />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <label className="flex items-center gap-2 text-sm text-zinc-700">
                  <input type="checkbox" className="h-4 w-4 rounded border-zinc-300" checked={internal} onChange={(e) => setInternal(e.target.checked)} />
                  Internal note
                </label>
                <Button type="submit" disabled={!body.trim() || reply.isPending}>
                  {internal ? "Add note" : "Send reply"}
                </Button>
              </div>
            </form>
          </div>
          <aside className="card space-y-4 p-4 text-sm lg:sticky lg:top-6">
            <label className="block">
              <span className="label">Status</span>
              <select className="input" disabled={update.isPending} value={t.status} onChange={(e) => update.mutate({ status: e.target.value })}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {TICKET_STATUS_LABELS[s]}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="label">Urgency</span>
              <select className="input" value={t.urgency} onChange={(e) => update.mutate({ urgency: e.target.value })}>
                {["low", "normal", "high"].map((u) => (
                  <option key={u}>{u}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="label">Assigned to</span>
              <input
                className="input"
                defaultValue={t.assigned_to ?? ""}
                placeholder="Name or email"
                onBlur={(e) => e.target.value !== (t.assigned_to ?? "") && update.mutate({ assigned_to: e.target.value })}
              />
            </label>
            <dl className="space-y-1 border-t border-zinc-100 pt-3 text-zinc-600">
              <div className="flex justify-between">
                <dt>Plan</dt>
                <dd>{PLAN[t.plan] ?? "—"}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Category</dt>
                <dd>{t.category}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Opened</dt>
                <dd>{formatDate(t.created_at)}</dd>
              </div>
            </dl>
            <Link to={`/admin/tenants/${t.company_id}`} className="block font-medium text-indigo-600 hover:text-indigo-700">
              Open {t.company_name} →
            </Link>
          </aside>
        </div>
      )}
    </Loading>
  );
}

// ---------------------------------------------------------------- contact requests

export function AdminContact() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("new");
  const query = useQuery({ queryKey: ["admin", "contact", status], queryFn: () => get("/admin/contact", status ? { status } : undefined) });
  const update = useMutation({
    mutationFn: ({ id, ...changes }) => apiClient.patch(`/admin/contact/${id}`, changes).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "contact"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "overview"] });
    },
  });
  return (
    <>
      <Title sub="Messages from the Contact us form on the public pages.">Contact requests</Title>
      <div className="mb-4 flex gap-2">
        {[
          ["new", "New"],
          ["contacted", "Contacted"],
          ["closed", "Closed"],
          ["", "All"],
        ].map(([value, label]) => (
          <button
            key={label}
            type="button"
            onClick={() => setStatus(value)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${status === value ? "bg-zinc-900 text-white" : "bg-white text-zinc-600 ring-1 ring-inset ring-zinc-200"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <Loading query={query}>
        {(rows) =>
          rows.length === 0 ? (
            <p className="card p-6 text-center text-sm text-zinc-500">No requests.</p>
          ) : (
            <ul className="space-y-3">
              {rows.map((c) => (
                <li key={c.id} className="card p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-zinc-900">
                        {c.name} {c.company && <span className="text-zinc-500">· {c.company}</span>} <Pill>{c.topic}</Pill>
                      </p>
                      <p className="text-sm text-zinc-500">
                        <a href={`mailto:${c.email}`} className="text-indigo-600 hover:underline">
                          {c.email}
                        </a>
                        {c.phone && ` · ${c.phone}`} · {formatDateTime(c.created_at)}
                      </p>
                    </div>
                    <select className="input !h-9 !w-auto !py-0 !text-sm" value={c.status} onChange={(e) => update.mutate({ id: c.id, status: e.target.value })}>
                      <option value="new">New</option>
                      <option value="contacted">Contacted</option>
                      <option value="closed">Closed</option>
                    </select>
                  </div>
                  <p className="mt-3 whitespace-pre-line text-sm text-zinc-700">{c.message}</p>
                  <input
                    className="input mt-3 !text-sm"
                    placeholder="Notes for the team…"
                    defaultValue={c.admin_notes ?? ""}
                    onBlur={(e) => e.target.value !== (c.admin_notes ?? "") && update.mutate({ id: c.id, admin_notes: e.target.value })}
                  />
                </li>
              ))}
            </ul>
          )
        }
      </Loading>
    </>
  );
}

// ---------------------------------------------------------------- sessions

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function AdminBookings() {
  const queryClient = useQueryClient();
  const bookings = useQuery({ queryKey: ["admin", "bookings"], queryFn: () => get("/admin/bookings") });
  const settings = useQuery({ queryKey: ["admin", "booking-settings"], queryFn: () => get("/admin/booking-settings") });
  const [form, setForm] = useState(null);
  const rules = form ?? settings.data;
  const save = useMutation({
    mutationFn: () => apiClient.put("/admin/booking-settings", { ...rules, blocked_dates: rules.blocked_dates.filter(Boolean) }).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.setQueryData(["admin", "booking-settings"], data);
      setForm(null);
      toast.success("Availability saved");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const cancel = useMutation({
    mutationFn: (id) => apiClient.post(`/admin/bookings/${id}/cancel`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "bookings"] });
      toast.success("Cancelled; they've been emailed");
    },
  });
  const set = (field, value) => setForm({ ...rules, [field]: value });
  return (
    <>
      <Title sub="Sessions companies booked with you. Each booking sends a calendar invite to your calendar and theirs.">Sessions</Title>
      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Loading query={bookings}>
          {(rows) =>
            rows.length === 0 ? (
              <p className="card p-6 text-center text-sm text-zinc-500">No upcoming sessions.</p>
            ) : (
              <ul className="card divide-y divide-zinc-100">
                {rows.map((b) => (
                  <li key={b.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                    <div>
                      <p className={`font-medium ${b.status === "cancelled" ? "text-zinc-400 line-through" : "text-zinc-900"}`}>{formatDateTime(b.starts_at)}</p>
                      <p className="text-sm text-zinc-500">
                        {b.topic} · {b.attendee_name} ({b.attendee_email}) · {b.company_name}
                      </p>
                      {b.notes && <p className="text-sm text-zinc-600">“{b.notes}”</p>}
                    </div>
                    {b.status === "booked" && (
                      <button type="button" className="text-sm font-medium text-rose-600 hover:text-rose-700" onClick={() => cancel.mutate(b.id)}>
                        Cancel
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )
          }
        </Loading>
        {rules && (
          <section className="card space-y-4 p-4 text-sm">
            <h2 className="font-semibold text-zinc-900">When people can book</h2>
            <label className="flex items-center gap-2">
              <input type="checkbox" className="h-4 w-4 rounded border-zinc-300" checked={rules.enabled} onChange={(e) => set("enabled", e.target.checked)} />
              Bookings open
            </label>
            <div>
              <span className="label">Days</span>
              <div className="flex flex-wrap gap-1.5">
                {WEEKDAYS.map((d, i) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => set("weekdays", rules.weekdays.includes(i) ? rules.weekdays.filter((x) => x !== i) : [...rules.weekdays, i].sort())}
                    className={`rounded-lg px-2.5 py-1 text-xs font-medium ${rules.weekdays.includes(i) ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-600"}`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="label">From</span>
                <input className="input" type="time" value={rules.start} onChange={(e) => set("start", e.target.value)} />
              </label>
              <label className="block">
                <span className="label">Until</span>
                <input className="input" type="time" value={rules.end} onChange={(e) => set("end", e.target.value)} />
              </label>
              <label className="block">
                <span className="label">Session length (min)</span>
                <input className="input" type="number" min="15" max="180" step="15" value={rules.slot_minutes} onChange={(e) => set("slot_minutes", Number(e.target.value))} />
              </label>
              <label className="block">
                <span className="label">Notice (hours)</span>
                <input className="input" type="number" min="0" max="720" value={rules.min_notice_hours} onChange={(e) => set("min_notice_hours", Number(e.target.value))} />
              </label>
              <label className="block">
                <span className="label">Days ahead</span>
                <input className="input" type="number" min="1" max="90" value={rules.days_ahead} onChange={(e) => set("days_ahead", Number(e.target.value))} />
              </label>
              <label className="block">
                <span className="label">Time zone</span>
                <input className="input" value={rules.timezone} onChange={(e) => set("timezone", e.target.value)} />
              </label>
            </div>
            <label className="block">
              <span className="label">Meeting link (Google Meet, Teams, Zoom)</span>
              <input className="input" value={rules.meeting_link ?? ""} placeholder="https://meet.google.com/…" onChange={(e) => set("meeting_link", e.target.value || null)} />
            </label>
            <label className="block">
              <span className="label">Days off (one per line, YYYY-MM-DD)</span>
              <textarea className="input min-h-[4.5rem]" value={rules.blocked_dates.join("\n")} onChange={(e) => set("blocked_dates", e.target.value.split("\n").map((s) => s.trim()))} />
            </label>
            <Button onClick={() => save.mutate()} disabled={!form || save.isPending}>
              Save availability
            </Button>
          </section>
        )}
      </div>
    </>
  );
}

// ---------------------------------------------------------------- errors and activity

function ErrorList({ rows, onOpen }) {
  if (!rows.length) return <p className="mt-2 text-sm text-zinc-500">No errors. 🎉</p>;
  return (
    <ul className="mt-2 divide-y divide-zinc-100 text-sm">
      {rows.map((e) => (
        <li key={e.id}>
          <button type="button" onClick={() => onOpen?.(e.id)} className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 py-2 text-left hover:bg-zinc-50">
            <span className={`font-mono text-xs ${e.resolved_at ? "text-zinc-400" : "text-rose-600"}`}>{e.error_type}</span>
            <span className="min-w-0 flex-1 truncate text-zinc-700">{e.message || "—"}</span>
            <span className="text-xs text-zinc-500">
              {e.company_name ?? "No company"} · {e.method ?? e.source} {e.path} · {formatDateTime(e.created_at)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function AdminErrors() {
  const queryClient = useQueryClient();
  const [resolved, setResolved] = useState(false);
  const [open, setOpen] = useState(null);
  const query = useQuery({ queryKey: ["admin", "errors", "all", resolved], queryFn: () => get("/admin/errors", { resolved }) });
  const detail = useQuery({ queryKey: ["admin", "error", open], queryFn: () => get(`/admin/errors/${open}`), enabled: Boolean(open) });
  const resolve = useMutation({
    mutationFn: (id) => apiClient.post(`/admin/errors/${id}/resolve`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "errors"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "overview"] });
      setOpen(null);
    },
  });
  return (
    <>
      <Title sub="Unexpected server errors and failed background jobs, across every company. People see a reference (the request id) they can quote in a ticket.">
        Error log
      </Title>
      <div className="mb-4 flex gap-2">
        {[
          [false, "To look at"],
          [true, "Resolved"],
        ].map(([value, label]) => (
          <button
            key={label}
            type="button"
            onClick={() => setResolved(value)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${resolved === value ? "bg-zinc-900 text-white" : "bg-white text-zinc-600 ring-1 ring-inset ring-zinc-200"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <Loading query={query}>{(rows) => <section className="card px-4 py-2">{<ErrorList rows={rows} onOpen={setOpen} />}</section>}</Loading>
      <Sheet
        open={Boolean(open)}
        onClose={() => setOpen(null)}
        title={detail.data?.error_type ?? "Error"}
        footer={
          detail.data && (
            <div className="flex justify-end">
              <Button variant="secondary" onClick={() => resolve.mutate(open)}>
                {detail.data.resolved_at ? "Mark as not resolved" : "Mark as resolved"}
              </Button>
            </div>
          )
        }
      >
        {detail.data && (
          <div className="space-y-3 text-sm">
            <dl className="grid grid-cols-[7rem_minmax(0,1fr)] gap-1">
              <dt className="text-zinc-500">When</dt>
              <dd>{formatDateTime(detail.data.created_at)}</dd>
              <dt className="text-zinc-500">Company</dt>
              <dd>{detail.data.company_name ?? "—"}</dd>
              <dt className="text-zinc-500">Where</dt>
              <dd className="break-all">
                {detail.data.method ?? detail.data.source} {detail.data.path}
              </dd>
              <dt className="text-zinc-500">Request id</dt>
              <dd className="font-mono">{detail.data.request_id ?? "—"}</dd>
            </dl>
            <p className="text-zinc-800">{detail.data.message}</p>
            <pre className="max-h-[50vh] overflow-auto rounded-lg bg-zinc-950 p-3 text-xs leading-relaxed text-zinc-200">{detail.data.traceback}</pre>
          </div>
        )}
      </Sheet>
    </>
  );
}

// "POST /invoices/{invoice_id}/send" -> "Sent an invoice"
const ACTIONS = [
  [/^POST \/auth\/login$/, "Signed in"],
  [/^POST \/auth\/register$/, "Signed up"],
  [/^POST \/invoices$/, "Created an invoice"],
  [/^POST \/invoices\/\{invoice_id\}\/send$/, "Sent an invoice"],
  [/^POST \/invoices\/\{invoice_id\}\/payments$/, "Recorded a payment"],
  [/^POST \/quotes$/, "Created a quote"],
  [/^POST \/customers$/, "Added a client"],
  [/^POST \/crm\/deals$|^POST \/deals$/, "Added a deal"],
  [/^POST \/support\/tickets$/, "Opened a support ticket"],
  [/^POST \/bookings$/, "Booked a session"],
  [/^POST \/billing\/checkout$/, "Started a plan checkout"],
  [/^POST \/imports\//, "Imported data"],
  [/^POST \/marketing\/campaigns\/\{campaign_id\}\/send$/, "Sent a marketing campaign"],
];
const describe = (row) => ACTIONS.find(([re]) => re.test(`${row.method} ${row.route}`))?.[1];

function ActivityTable({ rows, showCompany = true }) {
  return (
    <table className="w-full min-w-[44rem] text-sm">
      <thead className="table-head">
        <tr>
          <th>When</th>
          {showCompany && <th>Company</th>}
          <th>Who</th>
          <th>What</th>
          <th className="text-right">Result</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-zinc-100">
        {rows.map((r) => (
          <tr key={r.id}>
            <td className="whitespace-nowrap px-4 py-2 text-zinc-500">{formatDateTime(r.created_at)}</td>
            {showCompany && <td className="px-4 py-2">{r.company_name ?? "—"}</td>}
            <td className="px-4 py-2">{r.actor_email ?? "—"}</td>
            <td className="px-4 py-2">
              {describe(r) ?? <span className="font-mono text-xs text-zinc-600">{`${r.method} ${r.route}`}</span>}
            </td>
            <td className={`px-4 py-2 text-right tabular-nums ${r.status_code >= 400 ? "text-rose-600" : "text-zinc-500"}`}>{r.status_code}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function AdminActivity() {
  const [search, setSearch] = useState("");
  const query = useQuery({ queryKey: ["admin", "activity", "all", search], queryFn: () => get("/admin/activity", { search: search || undefined, limit: 200 }) });
  return (
    <>
      <Title sub="Every change made in every company: who, what and when (sign-ins included).">Activity</Title>
      <input type="search" className="input mb-4 max-w-sm" placeholder="Filter by email or action…" value={search} onChange={(e) => setSearch(e.target.value)} />
      <Loading query={query}>{(rows) => <section className="card overflow-x-auto">{<ActivityTable rows={rows} />}</section>}</Loading>
    </>
  );
}
