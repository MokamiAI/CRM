import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { usePurchaseOrder, usePurchaseOrders, useSupplierMap, useSuppliers } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import DocumentEditor from "../components/DocumentEditor";
import { BackLink, LineItems, SummaryCard } from "../components/DocumentView";
import Sheet from "../components/Sheet";
import { DocumentViewer } from "../components/Documents";
import { Avatar, Button, ButtonLink, EmptyState, ErrorState, Field, FilterChips, ListSkeleton, PageHeader, PlusIcon, StatusBadge } from "../components/ui";
import { errorMessage, formatDate, formatMoney, formatShortDate } from "../utils/format";

const STATUS_FILTERS = ["", "draft", "sent", "received", "cancelled"];

/** Buying from suppliers: purchase orders, and the suppliers they go to. */
export default function PurchaseOrdersPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "suppliers" ? "suppliers" : "orders";
  const canWrite = user?.role !== "viewer";
  const [adding, setAdding] = useState(false);

  return (
    <>
      <PageHeader
        title={t("nav.purchaseOrders")}
        subtitle={t("purchases.subtitle")}
        actions={
          canWrite &&
          (tab === "orders" ? (
            <ButtonLink to="/purchase-orders/new">
              <PlusIcon className="h-4 w-4" /> {t("purchases.new")}
            </ButtonLink>
          ) : (
            <Button onClick={() => setAdding(true)}>
              <PlusIcon className="h-4 w-4" /> {t("suppliers.add")}
            </Button>
          ))
        }
      />
      <div className="mb-4 flex gap-1 border-b border-zinc-200" role="tablist">
        {["orders", "suppliers"].map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setParams(key === "orders" ? {} : { tab: key }, { replace: true })}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors duration-150 ${
              tab === key ? "border-indigo-600 text-zinc-900" : "border-transparent text-zinc-500 hover:text-zinc-800"
            }`}
          >
            {t(`purchases.tabs.${key}`)}
          </button>
        ))}
      </div>
      {tab === "orders" ? <Orders /> : <Suppliers canWrite={canWrite} adding={adding} setAdding={setAdding} />}
    </>
  );
}

function Orders() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [status, setStatus] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const { data: suppliers = [] } = useSuppliers();
  const suppliersById = useSupplierMap();
  const { data, isLoading, isError, refetch } = usePurchaseOrders({ ...(status && { status }), ...(supplierId && { supplier_id: supplierId }) });
  const nameOf = (po) => suppliersById.get(po.supplier_id)?.name ?? "…";

  return (
    <>
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <select className="input sm:max-w-xs" aria-label={t("editor.supplier")} value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
          <option value="">{t("purchases.allSuppliers")}</option>
          {suppliers.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>
      <FilterChips options={STATUS_FILTERS.map((value) => ({ value, label: t(value ? `status.${value}` : "common.all") }))} value={status} onChange={setStatus} />
      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : data.length === 0 ? (
        <EmptyState title={t(status || supplierId ? "purchases.noneHere" : "purchases.none")} description={status || supplierId ? undefined : t("purchases.noneHint")} />
      ) : (
        <div className="card overflow-hidden">
          <table className="hidden w-full md:table">
            <thead className="table-head">
              <tr>
                <th>{t("purchases.col.number")}</th>
                <th>{t("editor.supplier")}</th>
                <th>{t("invoices.col.issued")}</th>
                <th>{t("purchases.deliverBy")}</th>
                <th>{t("invoices.col.status")}</th>
                <th className="text-right">{t("invoices.col.amount")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((po) => (
                <tr key={po.id} className="table-row" onClick={() => navigate(`/purchase-orders/${po.id}`)}>
                  <td className="whitespace-nowrap font-medium text-zinc-900">
                    <Link to={`/purchase-orders/${po.id}`} onClick={(e) => e.stopPropagation()} className="hover:underline">
                      {po.po_number}
                    </Link>
                    {po.reference && <span className="block text-xs font-normal text-zinc-500">{po.reference}</span>}
                  </td>
                  <td>
                    <div className="flex items-center gap-2.5">
                      <Avatar name={nameOf(po)} size="sm" />
                      <span className="truncate text-zinc-700">{nameOf(po)}</span>
                    </div>
                  </td>
                  <td className="whitespace-nowrap text-zinc-500">{formatShortDate(po.issue_date)}</td>
                  <td className="whitespace-nowrap text-zinc-500">{po.delivery_date ? formatShortDate(po.delivery_date) : "—"}</td>
                  <td>
                    <StatusBadge status={po.status} />
                  </td>
                  <td className="whitespace-nowrap text-right font-medium tabular-nums text-zinc-900">{formatMoney(po.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="divide-y divide-zinc-100 md:hidden">
            {data.map((po) => (
              <li key={po.id}>
                <Link to={`/purchase-orders/${po.id}`} className="flex items-center gap-3 px-4 py-3.5 transition-colors duration-150 active:bg-zinc-50">
                  <Avatar name={nameOf(po)} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-zinc-900">{nameOf(po)}</p>
                    <p className="truncate text-[13px] text-zinc-500">
                      {po.po_number}
                      {po.reference && ` · ${po.reference}`}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <p className="font-medium tabular-nums text-zinc-900">{formatMoney(po.total)}</p>
                    <StatusBadge status={po.status} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

const EMPTY_SUPPLIER = { name: "", contact_name: "", email: "", phone: "", tax_number: "", address: "", notes: "" };

function Suppliers({ canWrite, adding, setAdding }) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const { data, isLoading, isError, refetch } = useSuppliers({ ...(search.trim() && { search: search.trim() }), include_inactive: showInactive });
  const [editing, setEditing] = useState(null);
  const open = adding ? EMPTY_SUPPLIER : editing;

  return (
    <>
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <input className="input sm:max-w-xs" type="search" placeholder={t("suppliers.search")} aria-label={t("suppliers.search")} value={search} onChange={(e) => setSearch(e.target.value)} />
        <label className="flex items-center gap-2 text-sm text-zinc-600">
          <input type="checkbox" className="h-4 w-4" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          {t("suppliers.showInactive")}
        </label>
      </div>
      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : data.length === 0 ? (
        <EmptyState title={t(search ? "suppliers.noneFound" : "suppliers.none")} description={search ? undefined : t("suppliers.noneHint")} />
      ) : (
        <ul className="card divide-y divide-zinc-100">
          {data.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                disabled={!canWrite}
                onClick={() => setEditing(s)}
                className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors duration-150 hover:bg-zinc-50 disabled:cursor-default disabled:hover:bg-transparent"
              >
                <Avatar name={s.name} />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-zinc-900">{s.name}</p>
                  <p className="truncate text-[13px] text-zinc-500">{[s.contact_name, s.email, s.phone].filter(Boolean).join(" · ") || t("suppliers.noContact")}</p>
                </div>
                {!s.is_active && <StatusBadge status="inactive" />}
              </button>
            </li>
          ))}
        </ul>
      )}
      <SupplierSheet
        supplier={open}
        onClose={() => {
          setAdding(false);
          setEditing(null);
        }}
      />
    </>
  );
}

function SupplierSheet({ supplier, onClose }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_SUPPLIER);
  const [loadedFor, setLoadedFor] = useState(null);
  if (supplier && loadedFor !== supplier) {
    setLoadedFor(supplier);
    setForm(Object.fromEntries(Object.keys(EMPTY_SUPPLIER).map((k) => [k, supplier[k] ?? ""])));
  }
  const isNew = supplier && !supplier.id;
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));
  const done = (message) => {
    queryClient.invalidateQueries({ queryKey: ["suppliers"] });
    toast.success(message);
    onClose();
  };
  const save = useMutation({
    mutationFn: () => (isNew ? apiClient.post("/suppliers", form) : apiClient.patch(`/suppliers/${supplier.id}`, form)),
    onSuccess: () => done(t("suppliers.saved")),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const toggle = useMutation({
    mutationFn: () => apiClient.patch(`/suppliers/${supplier.id}`, { is_active: !supplier.is_active }),
    onSuccess: () => done(t(supplier.is_active ? "suppliers.deactivated" : "suppliers.reactivated")),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const fields = [
    ["name", { required: true, maxLength: 255, autoComplete: "organization" }],
    ["contact_name", { maxLength: 255 }],
    ["email", { type: "email", maxLength: 255 }],
    ["phone", { type: "tel", maxLength: 50 }],
    ["tax_number", { maxLength: 100 }],
  ];
  return (
    <Sheet
      open={Boolean(supplier)}
      onClose={onClose}
      title={t(isNew ? "suppliers.add" : "suppliers.edit")}
      footer={
        <>
          {!isNew && (
            <Button variant="secondary" className="mr-auto" disabled={toggle.isPending} onClick={() => toggle.mutate()}>
              {t(supplier?.is_active ? "suppliers.deactivate" : "suppliers.reactivate")}
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!form.name.trim() || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </>
      }
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (form.name.trim()) save.mutate();
        }}
      >
        {fields.map(([field, props]) => (
          <Field key={field} label={t(`suppliers.fields.${field}`)}>
            <input className="input" value={form[field]} onChange={set(field)} {...props} />
          </Field>
        ))}
        <Field label={t("suppliers.fields.address")}>
          <textarea className="input" rows={3} value={form.address} onChange={set("address")} />
        </Field>
        <Field label={t("suppliers.fields.notes")}>
          <textarea className="input" rows={2} value={form.notes} onChange={set("notes")} />
        </Field>
        <p className="text-xs text-zinc-500">{t("suppliers.emailHint")}</p>
      </form>
    </Sheet>
  );
}

export function NewPurchaseOrderPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const queryClient = useQueryClient();
  const create = useMutation({
    mutationFn: (payload) => apiClient.post("/purchase-orders", payload).then((res) => res.data),
    onSuccess: (po) => {
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
      toast.success(t("invoices.draftCreated", { number: po.po_number }));
      navigate(`/purchase-orders/${po.id}`, { replace: true });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <div className="max-w-4xl">
      <PageHeader eyebrow={<BackLink to="/purchase-orders">{t("nav.purchaseOrders")}</BackLink>} title={t("purchases.new")} subtitle={t("invoices.draftNote")} />
      <DocumentEditor
        kind="purchaseOrder"
        dateField="delivery_date"
        dateLabel={t("purchases.deliverBy")}
        dateHint={t("quotes.optional")}
        submitLabel={t("invoices.saveDraft")}
        isSubmitting={create.isPending}
        initialCustomerId={params.get("supplier") ?? undefined}
        onSubmit={(payload) => create.mutate(payload)}
      />
    </div>
  );
}

export function PurchaseOrderDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const { data: po, isLoading, isError, refetch } = usePurchaseOrder(id);
  const supplier = useSupplierMap().get(po?.supplier_id);
  const [sheet, setSheet] = useState(null);
  const [notify, setNotify] = useState(true);
  const queryClient = useQueryClient();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["purchase-order", id] });
    queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
  };
  const onError = (error) => toast.error(errorMessage(error));
  const action = useMutation({
    mutationFn: ({ path, params }) => apiClient.post(`/purchase-orders/${id}/${path}`, null, { params }),
    onSuccess: (_r, { message, description }) => {
      refresh();
      setSheet(null);
      toast.success(message, description ? { description } : undefined);
    },
    onError,
  });
  const remove = useMutation({
    mutationFn: () => apiClient.delete(`/purchase-orders/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
      toast.success(t("invoice.draftDeleted"));
      navigate("/purchase-orders", { replace: true });
    },
    onError,
  });

  if (isLoading) return <ListSkeleton rows={4} />;
  if (isError) return <ErrorState onRetry={refetch} />;
  const hasEmail = Boolean(supplier?.email);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={<BackLink to="/purchase-orders">{t("nav.purchaseOrders")}</BackLink>}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {po.po_number} <StatusBadge status={po.status} />
          </span>
        }
        subtitle={supplier?.name}
        actions={
          <>
            <Button variant="secondary" onClick={() => setSheet("view")}>
              {t("documents.view")}
            </Button>
            {canWrite && po.status === "draft" && (
              <>
                <ButtonLink variant="secondary" to={`/purchase-orders/${id}/edit`}>
                  {t("common.edit")}
                </ButtonLink>
                <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
                  {t("invoice.deleteDraft")}
                </Button>
                <Button onClick={() => setSheet("send")}>{t("purchases.send")}</Button>
              </>
            )}
            {canWrite && po.status === "sent" && (
              <>
                <Button variant="secondary" disabled={action.isPending} onClick={() => action.mutate({ path: "cancel", message: t("purchases.cancelled") })}>
                  {t("purchases.cancel")}
                </Button>
                {hasEmail && (
                  <Button variant="secondary" disabled={action.isPending} onClick={() => action.mutate({ path: "resend", message: t("purchases.resent"), description: supplier.email })}>
                    {t("purchases.resend")}
                  </Button>
                )}
                <Button disabled={action.isPending} onClick={() => action.mutate({ path: "receive", message: t("purchases.receivedToast") })}>
                  {t("purchases.markReceived")}
                </Button>
              </>
            )}
          </>
        }
      />

      <DocumentViewer open={sheet === "view"} onClose={() => setSheet(null)} url={`/purchase-orders/${po.id}/document`} title={`${po.po_number} · ${supplier?.name ?? ""}`} />

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <LineItems document={po} />
          {(po.delivery_address || po.notes) && (
            <section className="card space-y-4 p-5">
              {po.delivery_address && (
                <div>
                  <h2 className="mb-1.5 text-sm font-semibold text-zinc-900">{t("editor.deliveryAddress")}</h2>
                  <p className="whitespace-pre-line text-sm text-zinc-600">{po.delivery_address}</p>
                </div>
              )}
              {po.notes && (
                <div>
                  <h2 className="mb-1.5 text-sm font-semibold text-zinc-900">{t("editor.notes")}</h2>
                  <p className="whitespace-pre-line text-sm text-zinc-600">{po.notes}</p>
                </div>
              )}
            </section>
          )}
        </div>
        <aside className="min-w-0">
          <SummaryCard
            rows={[
              [t("editor.supplier"), supplier?.name ?? "…"],
              [t("invoices.col.issued"), formatDate(po.issue_date)],
              [t("purchases.deliverBy"), po.delivery_date ? formatDate(po.delivery_date) : "—"],
              ...(po.reference ? [[t("editor.reference"), po.reference]] : []),
              [t("document.lineItems"), po.items.length],
            ]}
            emphasis={[t("document.totalIncl"), formatMoney(po.total)]}
          />
        </aside>
      </div>

      <Sheet
        open={sheet === "send"}
        onClose={() => setSheet(null)}
        title={t("invoice.sendTitle", { number: po.po_number })}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSheet(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              disabled={action.isPending}
              onClick={() =>
                action.mutate({
                  path: "send",
                  params: { notify: notify && hasEmail },
                  message: t("purchases.sentToast"),
                  description: notify && hasEmail ? t("invoice.emailing", { email: supplier.email }) : undefined,
                })
              }
            >
              {action.isPending ? t("common.sending") : t("common.send")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-zinc-600">{t("purchases.sendBody", { total: formatMoney(po.total) })}</p>
        <label className="mt-4 flex items-start gap-3 rounded-lg border border-zinc-200 p-3">
          <input type="checkbox" className="mt-0.5 h-4 w-4" checked={notify && hasEmail} disabled={!hasEmail} onChange={(e) => setNotify(e.target.checked)} />
          <span className="text-sm">
            <span className="block font-medium text-zinc-900">{t("purchases.emailToSupplier")}</span>
            <span className="text-zinc-500">{hasEmail ? supplier.email : t("purchases.noEmail")}</span>
          </span>
        </label>
      </Sheet>
    </div>
  );
}
