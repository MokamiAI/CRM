import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useActivities, useContacts, useCustomer, useDeals, useInvoices, useQuotes, useTimeline } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import { useCustomFieldRows } from "../components/CustomFields";
import CustomerFormSheet from "../components/CustomerFormSheet";
import DealFormSheet from "../components/DealFormSheet";
import { NewConversationSheet } from "./MessagesPage";
import Sheet from "../components/Sheet";
import { BackLink } from "../components/DocumentView";
import { ActivityRow, ComposerSheet, NextActivityBadge, QuickActions, STAGE_LABELS, Timeline, useToggleActivity } from "../components/crm";
import { Avatar, Button, ButtonLink, ErrorState, Field, ListSkeleton, PlusIcon, StatusBadge } from "../components/ui";
import { errorMessage, formatDate, formatMoney } from "../utils/format";

const OPEN_INVOICE = ["sent", "partially_paid", "overdue"];

function Card({ title, action, children }) {
  return (
    <section className="card overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-zinc-100 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-zinc-900">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

const fullName = (c) => [c.first_name, c.last_name].filter(Boolean).join(" ");

export default function CustomerDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";

  const { data: customer, isLoading, isError, refetch } = useCustomer(id);
  const { data: contacts = [] } = useContacts(id);
  const { data: deals = [] } = useDeals({ status: "all", customer_id: id });
  const { data: invoices = [] } = useInvoices({ customer_id: id });
  const { data: quotes = [] } = useQuotes({ customer_id: id });
  const { data: activities = [] } = useActivities({ customer_id: id });
  const { data: timeline = [], isLoading: timelineLoading } = useTimeline("customer", id);
  const toggle = useToggleActivity();
  const customRows = useCustomFieldRows("customer", customer?.custom_fields);

  const [sheet, setSheet] = useState(null); // edit | deal | message | activity | note | contact
  const [editingContact, setEditingContact] = useState(null);
  const [composeType, setComposeType] = useState("call");
  const close = () => setSheet(null);

  if (isLoading) return <ListSkeleton rows={4} />;
  if (isError) return <ErrorState onRetry={refetch} />;

  const openActivities = activities.filter((a) => !a.done);
  const openDeals = deals.filter((d) => d.stage !== "won" && d.stage !== "lost");
  const openInvoices = invoices.filter((i) => OPEN_INVOICE.includes(i.status));
  const owed = openInvoices.reduce((t, i) => t + Number(i.total) - Number(i.amount_paid), 0);
  const lifetime = invoices.filter((i) => i.status !== "void").reduce((t, i) => t + Number(i.amount_paid), 0);

  return (
    <div className="space-y-6">
      {/* Record header: identity left, the main actions right. */}
      <div>
        <BackLink to="/customers">{t("nav.customers")}</BackLink>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-4">
            <span className="hidden sm:block">
              <Avatar name={customer.name} size="lg" />
            </span>
            <div className="min-w-0">
              <h1 className="flex flex-wrap items-center gap-3 text-2xl font-semibold text-zinc-900">
                {customer.name}
                {!customer.is_active && <StatusBadge status="inactive" />}
              </h1>
              <p className="mt-1 flex flex-wrap gap-x-3 text-sm text-zinc-500">
                {customer.email && (
                  <a href={`mailto:${customer.email}`} className="hover:text-zinc-900">
                    {customer.email}
                  </a>
                )}
                {customer.phone && (
                  <a href={`tel:${customer.phone}`} className="hover:text-zinc-900">
                    {customer.phone}
                  </a>
                )}
              </p>
            </div>
          </div>
          {canWrite && (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setSheet("edit")}>
                {t("common.edit")}
              </Button>
              {(customer.email || customer.phone) && (
                <Button variant="secondary" onClick={() => setSheet("message")}>
                  {t("messages.messageCustomer")}
                </Button>
              )}
              <ButtonLink variant="secondary" to={`/customers/${id}/statement`}>
                {t("statement.get")}
              </ButtonLink>
              <ButtonLink variant="secondary" to={`/invoices/new?customer=${id}`}>
                {t("dashboard.newInvoice")}
              </ButtonLink>
              <Button onClick={() => setSheet("deal")}>
                <PlusIcon className="h-4 w-4" /> {t("dashboard.newDeal")}
              </Button>
            </div>
          )}
        </div>

        <div className="mt-5">
          <QuickActions
            email={customer.email}
            phone={customer.phone}
            canWrite={canWrite}
            onCompose={({ mode, type }) => {
              if (type) setComposeType(type);
              setSheet(mode);
            }}
          />
        </div>

        {/* Key numbers at a glance. */}
        <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            [t("customer.owesYou"), formatMoney(owed)],
            [t("customer.paidToDate"), formatMoney(lifetime)],
            [t("customers.col.openDeals"), openDeals.length],
            [t("customer.pipeline"), formatMoney(openDeals.reduce((sum, d) => sum + Number(d.value), 0))],
          ].map(([label, value]) => (
            <div key={label} className="card px-4 py-3">
              <dt className="text-xs font-medium text-zinc-500">{label}</dt>
              <dd className="mt-1 text-lg font-semibold tracking-tight text-zinc-900">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-12">
        {/* Left: who they are */}
        <aside className="space-y-6 lg:col-span-3">
          <Card
            title={t("customer.people")}
            action={
              canWrite && (
                <button
                  type="button"
                  onClick={() => {
                    setEditingContact(null);
                    setSheet("contact");
                  }}
                  className="text-xs font-medium text-zinc-500 hover:text-zinc-900"
                >
                  {t("customer.add")}
                </button>
              )
            }
          >
            {contacts.length ? (
              <ul className="divide-y divide-zinc-100">
                {contacts.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      disabled={!canWrite}
                      onClick={() => {
                        setEditingContact(c);
                        setSheet("contact");
                      }}
                      className="flex w-full items-start gap-3 px-5 py-3 text-left enabled:hover:bg-zinc-50"
                    >
                      <Avatar name={fullName(c)} size="sm" />
                      <div className="min-w-0 text-sm">
                        <p className="flex items-center gap-2 font-medium text-zinc-900">
                          <span className="truncate">{fullName(c)}</span>
                          {c.is_primary && <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{t("customer.primary")}</span>}
                        </p>
                        {c.job_title && <p className="truncate text-xs text-zinc-500">{c.job_title}</p>}
                        {c.email && <p className="truncate text-xs text-zinc-500">{c.email}</p>}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-4 text-sm text-zinc-500">{t("customer.noPeople")}</p>
            )}
          </Card>
          <Card title={t("customer.about")}>
            <dl className="space-y-3 p-5 text-sm">
              {[
                [t("customerForm.address"), customer.billing_address],
                [t("customerForm.taxNumber"), customer.tax_number],
                [t("customerForm.background"), customer.notes],
                ...customRows,
                [
                  t("customerForm.marketing"),
                  customer.marketing_opt_out
                    ? t("customer.unsubscribedOn", { date: formatDate(customer.marketing_opt_out_at) })
                    : t("customer.subscribed"),
                ],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs text-zinc-500">{label}</dt>
                  <dd className="mt-0.5 whitespace-pre-line text-zinc-900">{value || <span className="text-zinc-400">—</span>}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </aside>

        {/* Middle: what's next, then the whole history */}
        <div className="min-w-0 space-y-6 lg:col-span-6">
          <Card
            title={t("deal.nextSteps")}
            action={
              canWrite && (
                <div className="flex gap-1.5">
                  <Button variant="secondary" className="!h-8 !px-2.5 !text-xs" onClick={() => setSheet("note")}>
                    {t("composer.addNote")}
                  </Button>
                  <Button className="!h-8 !px-2.5 !text-xs" onClick={() => setSheet("activity")}>
                    <PlusIcon className="h-3.5 w-3.5" /> {t("composer.schedule")}
                  </Button>
                </div>
              )
            }
          >
            {openActivities.length ? (
              <ul className="divide-y divide-zinc-100">
                {openActivities.map((a) => (
                  <ActivityRow key={a.id} activity={a} onToggle={toggle.mutate} />
                ))}
              </ul>
            ) : (
              <p className="px-5 py-4 text-sm text-zinc-500">Nothing scheduled with {customer.name}.</p>
            )}
          </Card>
          <Card title={t("customer.timeline")}>
            <Timeline items={timeline} loading={timelineLoading} />
          </Card>
        </div>

        {/* Right: everything linked to them */}
        <aside className="space-y-6 lg:col-span-3">
          <Card title={`${t("nav.deals")}${deals.length ? ` · ${deals.length}` : ""}`}>
            {deals.length ? (
              <ul className="divide-y divide-zinc-100">
                {deals.map((d) => (
                  <li key={d.id}>
                    <Link to={`/deals/${d.id}`} className="block px-5 py-3 hover:bg-zinc-50">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-sm font-medium text-zinc-900">{d.title}</span>
                        <span className="shrink-0 text-sm tabular-nums text-zinc-700">{formatMoney(d.value)}</span>
                      </div>
                      <div className="mt-1 flex items-center justify-between gap-2 text-xs text-zinc-500">
                        <span>{STAGE_LABELS[d.stage]}</span>
                        {d.stage !== "won" && d.stage !== "lost" && <NextActivityBadge activity={d.next_activity} />}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-4 text-sm text-zinc-500">{t("customer.noDeals")}</p>
            )}
          </Card>
          <Card
            title={`${t("nav.invoices")}${invoices.length ? ` · ${invoices.length}` : ""}`}
            action={
              canWrite && (
                <Link to={`/invoices/new?customer=${id}`} className="text-xs font-medium text-zinc-500 hover:text-zinc-900">
                  {t("customer.new")}
                </Link>
              )
            }
          >
            <RecordList
              items={invoices.slice(0, 6)}
              empty={t("customer.noInvoices")}
              render={(i) => ({ to: `/invoices/${i.id}`, title: i.invoice_number, amount: i.total, status: i.status })}
            />
          </Card>
          <Card
            title={`${t("nav.quotes")}${quotes.length ? ` · ${quotes.length}` : ""}`}
            action={
              canWrite && (
                <Link to={`/quotes/new?customer=${id}`} className="text-xs font-medium text-zinc-500 hover:text-zinc-900">
                  {t("customer.new")}
                </Link>
              )
            }
          >
            <RecordList
              items={quotes.slice(0, 6)}
              empty={t("deal.noQuotes")}
              render={(q) => ({ to: `/quotes/${q.id}`, title: q.quote_number, amount: q.total, status: q.status })}
            />
          </Card>
        </aside>
      </div>

      <CustomerFormSheet open={sheet === "edit"} onClose={close} customer={customer} />
      <DealFormSheet open={sheet === "deal"} onClose={close} deal={null} customerId={id} />
      <NewConversationSheet open={sheet === "message"} onClose={close} customerId={id} />
      <ComposerSheet open={sheet === "activity"} onClose={close} mode="activity" customerId={id} initialType={composeType} />
      <ComposerSheet open={sheet === "note"} onClose={close} mode="note" customerId={id} />
      <ContactSheet open={sheet === "contact"} onClose={close} customerId={id} contact={editingContact} />
    </div>
  );
}

function RecordList({ items, empty, render }) {
  if (!items.length) return <p className="px-5 py-4 text-sm text-zinc-500">{empty}</p>;
  return (
    <ul className="divide-y divide-zinc-100">
      {items.map((item) => {
        const row = render(item);
        return (
          <li key={row.to}>
            <Link to={row.to} className="flex items-center justify-between gap-2 px-5 py-3 text-sm hover:bg-zinc-50">
              <span className="whitespace-nowrap font-medium text-zinc-900">{row.title}</span>
              <span className="flex items-center gap-2">
                <span className="tabular-nums text-zinc-700">{formatMoney(row.amount)}</span>
                <StatusBadge status={row.status} />
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

const EMPTY_CONTACT = { first_name: "", last_name: "", email: "", phone: "", job_title: "", is_primary: false };

function ContactSheet({ open, onClose, customerId, contact }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_CONTACT);
  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) setForm(contact ? Object.fromEntries(Object.keys(EMPTY_CONTACT).map((k) => [k, contact[k] ?? (k === "is_primary" ? false : "")])) : EMPTY_CONTACT);
  }
  const done = (message) => {
    queryClient.invalidateQueries({ queryKey: ["contacts", customerId] });
    toast.success(message);
    onClose();
  };
  const save = useMutation({
    mutationFn: () => {
      const payload = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === "" ? null : v]));
      return contact ? apiClient.patch(`/contacts/${contact.id}`, payload) : apiClient.post(`/customers/${customerId}/contacts`, payload);
    },
    onSuccess: () => done(t(contact ? "contact.updated" : "contact.added")),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: () => apiClient.delete(`/contacts/${contact.id}`),
    onSuccess: () => done(t("contact.removed")),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const set = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t(contact ? "contact.editTitle" : "contact.addTitle")}
      footer={
        <>
          {contact && (
            <Button variant="danger" className="mr-auto" disabled={remove.isPending} onClick={() => remove.mutate()}>
              {t("editor.remove")}
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="contact-form" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? t("common.saving") : t("common.save")}
          </button>
        </>
      }
    >
      <form
        id="contact-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("contact.firstName")}>
            <input className="input" required autoComplete="off" value={form.first_name} onChange={set("first_name")} />
          </Field>
          <Field label={t("contact.lastName")}>
            <input className="input" autoComplete="off" value={form.last_name} onChange={set("last_name")} />
          </Field>
        </div>
        <Field label={t("contact.jobTitle")}>
          <input className="input" value={form.job_title} onChange={set("job_title")} />
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("login.email")}>
            <input className="input" type="email" autoCapitalize="none" autoCorrect="off" value={form.email} onChange={set("email")} />
          </Field>
          <Field label={t("customerForm.phone")}>
            <input className="input" type="tel" value={form.phone} onChange={set("phone")} />
          </Field>
        </div>
        <label className="flex items-center gap-3 text-sm text-zinc-700">
          <input type="checkbox" className="h-4 w-4" checked={form.is_primary} onChange={(e) => setForm((p) => ({ ...p, is_primary: e.target.checked }))} />
          {t("contact.primary")}
        </label>
      </form>
    </Sheet>
  );
}
