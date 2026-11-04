// What the business spends, one-off or recurring, beside what came in
// (backend app/services/cost_service.py). Money counts when it moves:
// money in is payments received, money out is costs paid. For admins and
// managers only: salaries are in here.
import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { useSupplierMap, useSuppliers } from "../hooks/useApi";
import Sheet from "../components/Sheet";
import { Link } from "react-router-dom";
import { useHasFeature } from "../components/Billing";
import { Button, EmptyState, ErrorState, Field, FilterChips, ListSkeleton, PageHeader, PlusIcon } from "../components/ui";
import { errorMessage, formatDate, formatMoney } from "../utils/format";

export const PRESET_CATEGORIES = ["rent", "salaries", "stock", "transport", "marketing", "utilities", "software", "other"];
const FREQUENCIES = ["weekly", "monthly", "quarterly", "yearly"];
const NEW_CATEGORY = "__new";
const get = (path, params) => apiClient.get(path, { params }).then((r) => r.data);
const todayIso = () => new Date().toLocaleDateString("en-CA");
const thisMonth = () => todayIso().slice(0, 7);

export function categoryLabel(category, t) {
  return PRESET_CATEGORIES.includes(category) ? t(`costs.category.${category}`) : category;
}

function shiftMonth(month, by) {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + by, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function monthName(month, language) {
  const [y, m] = month.split("-").map(Number);
  return new Intl.DateTimeFormat(language, { month: "long", year: "numeric" }).format(new Date(y, m - 1, 1));
}

export function useMoneySummary(month) {
  return useQuery({ queryKey: ["costs", "summary", month], queryFn: () => get("/costs/summary", { month }) });
}

function useInvalidateCosts() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["costs"] });
}

function Stat({ label, value, hint, tone = "zinc" }) {
  const tones = { zinc: "text-zinc-900", emerald: "text-emerald-700", red: "text-red-600", amber: "text-amber-700" };
  return (
    <div className="card p-4">
      <p className="text-xs font-medium text-zinc-500">{label}</p>
      <p className={`mt-1 text-xl font-semibold tabular-nums ${tones[tone]}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-zinc-500">{hint}</p>}
    </div>
  );
}

function PaidBadge({ status, due }) {
  const { t } = useTranslation();
  const overdue = status === "due" && due < todayIso();
  const cls = status === "paid" ? "bg-emerald-50 text-emerald-700 ring-emerald-200/70" : overdue ? "bg-red-50 text-red-700 ring-red-200/70" : "bg-amber-50 text-amber-700 ring-amber-200/70";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}>
      {t(status === "paid" ? "costs.paid" : overdue ? "costs.overdue" : "costs.toPay")}
    </span>
  );
}

/** Ready-made categories, the company's own, or a new one typed in. */
function CategoryPicker({ value, onChange }) {
  const { t } = useTranslation();
  const { data: used = [] } = useQuery({ queryKey: ["costs", "categories"], queryFn: () => get("/costs/categories") });
  const own = used.filter((c) => !PRESET_CATEGORIES.includes(c));
  const known = PRESET_CATEGORIES.includes(value) || own.includes(value);
  const [typing, setTyping] = useState(Boolean(value) && !known);
  return (
    <div className="space-y-2">
      <select
        className="input"
        value={typing ? NEW_CATEGORY : value}
        onChange={(e) => {
          const next = e.target.value;
          setTyping(next === NEW_CATEGORY);
          onChange(next === NEW_CATEGORY ? "" : next);
        }}
      >
        {PRESET_CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {t(`costs.category.${c}`)}
          </option>
        ))}
        {own.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
        <option value={NEW_CATEGORY}>{t("costs.newCategory")}</option>
      </select>
      {typing && <input className="input" autoFocus maxLength={60} placeholder={t("costs.newCategoryHint")} value={value} onChange={(e) => onChange(e.target.value)} />}
    </div>
  );
}

function SupplierPicker({ value, onChange }) {
  const { t } = useTranslation();
  const { data: suppliers = [] } = useSuppliers();
  return (
    <select className="input" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">{t("costs.noSupplier")}</option>
      {suppliers.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </select>
  );
}

function Receipt({ cost }) {
  const { t } = useTranslation();
  const invalidate = useInvalidateCosts();
  const input = useRef(null);
  const upload = useMutation({
    mutationFn: (file) => {
      const form = new FormData();
      form.append("file", file);
      return apiClient.post(`/costs/${cost.id}/receipt`, form);
    },
    onSuccess: () => {
      invalidate();
      toast.success(t("costs.receiptAdded"));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({ mutationFn: () => apiClient.delete(`/costs/${cost.id}/receipt`), onSuccess: invalidate, onError: (error) => toast.error(errorMessage(error)) });
  async function open() {
    try {
      const { data } = await apiClient.get(`/costs/${cost.id}/receipt`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = cost.receipt_name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch (error) {
      toast.error(errorMessage(error));
    }
  }
  return (
    <div className="rounded-xl border border-dashed border-zinc-300 p-3 text-sm">
      <input ref={input} type="file" accept="image/*,.pdf,.heic" className="hidden" onChange={(e) => e.target.files[0] && upload.mutate(e.target.files[0])} />
      {cost.receipt_name ? (
        <div className="flex items-center justify-between gap-3">
          <button type="button" className="min-w-0 truncate font-medium text-blue-600 hover:underline" onClick={open}>
            {cost.receipt_name}
          </button>
          <span className="flex shrink-0 gap-3">
            <button type="button" className="text-zinc-500 hover:text-zinc-900" onClick={() => input.current.click()}>
              {t("costs.replaceReceipt")}
            </button>
            <button type="button" className="text-red-600 hover:text-red-700" onClick={() => remove.mutate()}>
              {t("costs.removeReceipt")}
            </button>
          </span>
        </div>
      ) : (
        <button type="button" disabled={upload.isPending} className="w-full text-left text-zinc-600 hover:text-zinc-900" onClick={() => input.current.click()}>
          {upload.isPending ? t("costs.uploading") : t("costs.addReceipt")}
        </button>
      )}
    </div>
  );
}

/** Add a cost, or change one: details, paid or not, the receipt. */
function CostSheet({ open, cost: picked, onClose }) {
  const { t } = useTranslation();
  const invalidate = useInvalidateCosts();
  const editing = Boolean(picked?.id);
  // Kept fresh while open, so an added receipt shows straight away.
  const { data: cost = picked } = useQuery({ queryKey: ["costs", "one", picked?.id], queryFn: () => get(`/costs/${picked.id}`), enabled: open && editing, initialData: picked ?? undefined });
  const blank = { description: "", amount: "", category: "stock", due_date: todayIso(), paid: true, supplier_id: null, notes: "" };
  const [form, setForm] = useState(blank);
  const [loadedFor, setLoadedFor] = useState(null);
  const key = open ? cost?.id ?? "new" : null;
  if (key !== loadedFor) {
    setLoadedFor(key);
    if (open) setForm(editing ? { ...cost, amount: String(Number(cost.amount)), paid: cost.status === "paid", notes: cost.notes ?? "" } : blank);
  }
  const set = (field) => (value) => setForm((f) => ({ ...f, [field]: value }));
  const onError = (error) => toast.error(errorMessage(error));
  const done = (message) => {
    invalidate();
    toast.success(message);
    onClose();
  };
  const save = useMutation({
    mutationFn: () => {
      const body = { description: form.description, amount: form.amount, category: form.category.trim(), due_date: form.due_date, supplier_id: form.supplier_id, notes: form.notes || null };
      if (editing && cost.status === "paid") body.paid_date = form.paid_date;
      return editing ? apiClient.patch(`/costs/${cost.id}`, body) : apiClient.post("/costs", { ...body, paid: form.paid });
    },
    onSuccess: () => done(t(editing ? "costs.updated" : "costs.added")),
    onError,
  });
  const togglePaid = useMutation({
    mutationFn: () => (cost.status === "paid" ? apiClient.post(`/costs/${cost.id}/unpaid`) : apiClient.post(`/costs/${cost.id}/paid`, {})),
    onSuccess: () => done(t(cost.status === "paid" ? "costs.markedUnpaid" : "costs.markedPaid")),
    onError,
  });
  const remove = useMutation({ mutationFn: () => apiClient.delete(`/costs/${cost.id}`), onSuccess: () => done(t("costs.deleted")), onError });
  const valid = form.description.trim() && Number(form.amount) > 0 && form.category.trim() && form.due_date;

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t(editing ? "costs.edit" : "costs.add")}
      footer={
        <>
          {editing && (
            <Button variant="danger" className="mr-auto" disabled={remove.isPending} onClick={() => window.confirm(t("costs.deleteConfirm")) && remove.mutate()}>
              {t("common.delete")}
            </Button>
          )}
          {editing && (
            <Button variant="secondary" disabled={togglePaid.isPending} onClick={() => togglePaid.mutate()}>
              {t(cost.status === "paid" ? "costs.markUnpaid" : "costs.markPaid")}
            </Button>
          )}
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            {t(editing ? "edit.save" : "costs.add")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label={t("costs.description")}>
          <input className="input" autoFocus={!editing} maxLength={255} placeholder={t("costs.descriptionHint")} value={form.description} onChange={(e) => set("description")(e.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("costs.amount")} hint={t("costs.amountHint")}>
            <input className="input tabular-nums" type="number" min="0.01" step="0.01" inputMode="decimal" value={form.amount} onChange={(e) => set("amount")(e.target.value)} />
          </Field>
          <Field label={t("costs.categoryLabel")}>
            <CategoryPicker value={form.category} onChange={set("category")} />
          </Field>
        </div>
        {!editing && (
          <FilterChips
            bare
            label={t("costs.paidQuestion")}
            options={[
              { value: true, label: t("costs.alreadyPaid") },
              { value: false, label: t("costs.payLater") },
            ]}
            value={form.paid}
            onChange={set("paid")}
          />
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          {editing && cost.status === "paid" ? (
            <Field label={t("costs.paidOn")}>
              <input className="input" type="date" value={form.paid_date ?? ""} onChange={(e) => set("paid_date")(e.target.value)} />
            </Field>
          ) : (
            <Field label={t(form.paid && !editing ? "costs.paidOn" : "costs.dueOn")}>
              <input className="input" type="date" value={form.due_date} onChange={(e) => set("due_date")(e.target.value)} />
            </Field>
          )}
          <Field label={t("costs.supplier")}>
            <SupplierPicker value={form.supplier_id} onChange={set("supplier_id")} />
          </Field>
        </div>
        <Field label={t("costs.notes")}>
          <textarea className="input" rows={2} value={form.notes} onChange={(e) => set("notes")(e.target.value)} />
        </Field>
        {editing ? (
          <Field label={t("costs.receipt")}>
            <Receipt cost={cost} />
          </Field>
        ) : (
          <p className="text-xs text-zinc-500">{t("costs.receiptLater")}</p>
        )}
      </div>
    </Sheet>
  );
}

/** A bill that comes back: rent, salaries, insurance. */
function RecurringSheet({ open, schedule, onClose }) {
  const { t } = useTranslation();
  const invalidate = useInvalidateCosts();
  const editing = Boolean(schedule?.id);
  const blank = { description: "", amount: "", category: "rent", frequency: "monthly", start_date: todayIso(), end_date: "", supplier_id: null, notes: "" };
  const [form, setForm] = useState(blank);
  const [loadedFor, setLoadedFor] = useState(null);
  const key = open ? schedule?.id ?? "new" : null;
  if (key !== loadedFor) {
    setLoadedFor(key);
    if (open) setForm(editing ? { ...schedule, amount: String(Number(schedule.amount)), start_date: schedule.next_run_date, end_date: schedule.end_date ?? "", notes: schedule.notes ?? "" } : blank);
  }
  const set = (field) => (value) => setForm((f) => ({ ...f, [field]: value }));
  const onError = (error) => toast.error(errorMessage(error));
  const done = (message) => {
    invalidate();
    toast.success(message);
    onClose();
  };
  const save = useMutation({
    mutationFn: () => {
      const body = { description: form.description, amount: form.amount, category: form.category.trim(), frequency: form.frequency, end_date: form.end_date || null, supplier_id: form.supplier_id, notes: form.notes || null };
      return editing ? apiClient.patch(`/recurring-costs/${schedule.id}`, { ...body, next_run_date: form.start_date }) : apiClient.post("/recurring-costs", { ...body, start_date: form.start_date });
    },
    onSuccess: () => done(t(editing ? "costs.recurringUpdated" : "costs.recurringAdded")),
    onError,
  });
  const toggle = useMutation({
    mutationFn: () => apiClient.post(`/recurring-costs/${schedule.id}/${schedule.active ? "pause" : "resume"}`),
    onSuccess: () => done(t(schedule.active ? "costs.paused" : "costs.resumed")),
    onError,
  });
  const remove = useMutation({ mutationFn: () => apiClient.delete(`/recurring-costs/${schedule.id}`), onSuccess: () => done(t("costs.recurringDeleted")), onError });
  const valid = form.description.trim() && Number(form.amount) > 0 && form.category.trim() && form.start_date;

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t(editing ? "costs.editRecurring" : "costs.addRecurring")}
      footer={
        <>
          {editing && (
            <Button variant="danger" className="mr-auto" disabled={remove.isPending} onClick={() => window.confirm(t("costs.recurringDeleteConfirm")) && remove.mutate()}>
              {t("common.delete")}
            </Button>
          )}
          {editing && (
            <Button variant="secondary" disabled={toggle.isPending} onClick={() => toggle.mutate()}>
              {t(schedule.active ? "costs.pause" : "costs.resume")}
            </Button>
          )}
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            {t(editing ? "edit.save" : "costs.addRecurring")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label={t("costs.description")}>
          <input className="input" autoFocus={!editing} maxLength={255} placeholder={t("costs.recurringHint")} value={form.description} onChange={(e) => set("description")(e.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("costs.amount")} hint={t("costs.amountHint")}>
            <input className="input tabular-nums" type="number" min="0.01" step="0.01" inputMode="decimal" value={form.amount} onChange={(e) => set("amount")(e.target.value)} />
          </Field>
          <Field label={t("costs.categoryLabel")}>
            <CategoryPicker value={form.category} onChange={set("category")} />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label={t("recurring.frequency")}>
            <select className="input" value={form.frequency} onChange={(e) => set("frequency")(e.target.value)}>
              {FREQUENCIES.map((f) => (
                <option key={f} value={f}>
                  {t(`recurring.every.${f}`)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t(editing ? "costs.nextDue" : "costs.firstDue")}>
            <input className="input" type="date" value={form.start_date} onChange={(e) => set("start_date")(e.target.value)} />
          </Field>
          <Field label={t("recurring.endsOn")} hint={t("recurring.endsHint")}>
            <input className="input" type="date" value={form.end_date} onChange={(e) => set("end_date")(e.target.value)} />
          </Field>
        </div>
        <Field label={t("costs.supplier")}>
          <SupplierPicker value={form.supplier_id} onChange={set("supplier_id")} />
        </Field>
        <p className="rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-800">{t("costs.recurringExplain")}</p>
      </div>
    </Sheet>
  );
}

function MarkPaid({ cost }) {
  const { t } = useTranslation();
  const invalidate = useInvalidateCosts();
  const pay = useMutation({
    mutationFn: () => apiClient.post(`/costs/${cost.id}/paid`, {}),
    onSuccess: () => {
      invalidate();
      toast.success(t("costs.markedPaid"));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <Button variant="secondary" className="!px-3 !py-1.5 text-xs" disabled={pay.isPending} onClick={(e) => (e.stopPropagation(), pay.mutate())}>
      {t("costs.markPaid")}
    </Button>
  );
}

export default function CostsPage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const allowed = ["admin", "manager"].includes(user?.role);
  const dashboard = useHasFeature("reports") === true;
  const [month, setMonth] = useState(thisMonth);
  const [view, setView] = useState("all");
  const [category, setCategory] = useState("");
  const [sheet, setSheet] = useState(null); // {kind: "cost" | "recurring", item}
  const suppliers = useSupplierMap();
  const summary = useMoneySummary(month);
  const [from, to] = useMemo(() => {
    const [y, m] = month.split("-").map(Number);
    return [`${month}-01`, new Date(y, m, 0).toLocaleDateString("en-CA")];
  }, [month]);
  const costs = useQuery({
    queryKey: ["costs", "list", view, category, month],
    queryFn: () => get("/costs", { ...(view === "all" ? { from, to } : view === "due" ? { status: "due" } : { status: "paid", from, to }), ...(category ? { category } : {}) }),
    enabled: allowed && view !== "recurring",
  });
  const recurring = useQuery({ queryKey: ["costs", "recurring"], queryFn: () => get("/recurring-costs"), enabled: allowed });
  const { data: used = [] } = useQuery({ queryKey: ["costs", "categories"], queryFn: () => get("/costs/categories"), enabled: allowed });

  if (!allowed) return <EmptyState title={t("costs.title")} description={t("costs.notAllowed")} />;
  const s = summary.data;
  const actions = (
    <>
      <Button variant="secondary" onClick={() => setSheet({ kind: "recurring" })}>
        {t("costs.addRecurring")}
      </Button>
      <Button onClick={() => setSheet({ kind: "cost" })}>
        <PlusIcon className="h-4 w-4" /> {t("costs.add")}
      </Button>
    </>
  );

  return (
    <>
      <PageHeader title={t("costs.title")} subtitle={t("costs.subtitle")} actions={actions} />
      {dashboard && (
        <Link to="/money" className="mb-4 inline-flex text-sm font-medium text-blue-600 hover:underline">
          {t("costs.seeDashboard")} →
        </Link>
      )}

      <div className="mb-3 flex items-center gap-2">
        <button type="button" className="pressable rounded-lg px-2 py-1 text-zinc-500 hover:bg-zinc-100" aria-label={t("costs.prevMonth")} onClick={() => setMonth((m) => shiftMonth(m, -1))}>
          ‹
        </button>
        <h2 className="min-w-[9rem] text-center text-sm font-semibold capitalize text-zinc-900">{monthName(month, i18n.language)}</h2>
        <button type="button" disabled={month >= thisMonth()} className="pressable rounded-lg px-2 py-1 text-zinc-500 hover:bg-zinc-100 disabled:opacity-30" aria-label={t("costs.nextMonth")} onClick={() => setMonth((m) => shiftMonth(m, 1))}>
          ›
        </button>
      </div>
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("costs.moneyIn")} value={s ? formatMoney(s.money_in) : "…"} hint={t("costs.moneyInHint")} />
        <Stat label={t("costs.moneyOut")} value={s ? formatMoney(s.money_out) : "…"} hint={t("costs.moneyOutHint")} />
        <Stat
          label={t("costs.profit")}
          value={s ? formatMoney(s.profit) : "…"}
          tone={s && Number(s.profit) < 0 ? "red" : "emerald"}
          hint={s?.margin != null ? t("costs.margin", { value: Number(s.margin).toLocaleString(i18n.language) }) : t("costs.noMargin")}
        />
        <Stat
          label={t("costs.stillToPay")}
          value={s ? formatMoney(s.to_pay) : "…"}
          tone={s?.overdue ? "red" : "amber"}
          hint={s?.overdue ? t("costs.overdueCount", { count: s.overdue }) : t("costs.allDates")}
        />
      </div>

      {s?.upcoming?.length > 0 && (
        <section className="card mb-6">
          <h2 className="border-b border-zinc-100 px-4 py-3 text-sm font-semibold text-zinc-900">{t("costs.billsDue")}</h2>
          <ul className="divide-y divide-zinc-100">
            {s.upcoming.map((c) => (
              <li key={c.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setSheet({ kind: "cost", item: c })}>
                  <span className="block truncate font-medium text-zinc-900">{c.description}</span>
                  <span className="text-xs text-zinc-500">
                    {t("costs.dueDate", { date: formatDate(c.due_date) })} · {categoryLabel(c.category, t)}
                  </span>
                </button>
                <PaidBadge status={c.status} due={c.due_date} />
                <span className="w-24 shrink-0 text-right font-semibold tabular-nums text-zinc-900">{formatMoney(c.amount)}</span>
                <MarkPaid cost={c} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <FilterChips
          bare
          label={t("costs.show")}
          options={[
            { value: "all", label: t("costs.thisMonthAll") },
            { value: "due", label: t("costs.toPay") },
            { value: "paid", label: t("costs.paid") },
            { value: "recurring", label: t("costs.recurring") },
          ]}
          value={view}
          onChange={setView}
        />
        {view !== "recurring" && (
          <select className="input !w-auto" value={category} onChange={(e) => setCategory(e.target.value)} aria-label={t("costs.categoryLabel")}>
            <option value="">{t("costs.allCategories")}</option>
            {[...new Set([...PRESET_CATEGORIES, ...used])].map((c) => (
              <option key={c} value={c}>
                {categoryLabel(c, t)}
              </option>
            ))}
          </select>
        )}
      </div>

      {view === "recurring" ? (
        recurring.isLoading ? (
          <ListSkeleton />
        ) : recurring.isError ? (
          <ErrorState onRetry={recurring.refetch} />
        ) : recurring.data.length === 0 ? (
          <EmptyState title={t("costs.noRecurring")} description={t("costs.noRecurringHint")} action={<Button onClick={() => setSheet({ kind: "recurring" })}>{t("costs.addRecurring")}</Button>} />
        ) : (
          <ul className="card divide-y divide-zinc-100">
            {recurring.data.map((r) => (
              <li key={r.id}>
                <button type="button" className="flex w-full items-center gap-4 px-4 py-3 text-left hover:bg-zinc-50" onClick={() => setSheet({ kind: "recurring", item: r })}>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-zinc-900">{r.description}</span>
                    <span className="text-xs text-zinc-500">
                      {t(`recurring.every.${r.frequency}`)} · {categoryLabel(r.category, t)}
                      {r.active ? ` · ${t("costs.nextDueOn", { date: formatDate(r.next_run_date) })}` : ` · ${t("recurring.paused")}`}
                    </span>
                  </span>
                  <span className="shrink-0 font-semibold tabular-nums text-zinc-900">{formatMoney(r.amount)}</span>
                </button>
              </li>
            ))}
          </ul>
        )
      ) : costs.isLoading ? (
        <ListSkeleton />
      ) : costs.isError ? (
        <ErrorState onRetry={costs.refetch} />
      ) : costs.data.items.length === 0 ? (
        <EmptyState title={t("costs.empty")} description={t("costs.emptyHint")} action={<Button onClick={() => setSheet({ kind: "cost" })}>{t("costs.add")}</Button>} />
      ) : (
        <section className="card">
          <ul className="divide-y divide-zinc-100">
            {costs.data.items.map((c) => (
              <li key={c.id}>
                <button type="button" className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-zinc-50" onClick={() => setSheet({ kind: "cost", item: c })}>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-zinc-900">{c.description}</span>
                    <span className="text-xs text-zinc-500">
                      {formatDate(c.paid_date ?? c.due_date)} · {categoryLabel(c.category, t)}
                      {c.supplier_id && suppliers.get(c.supplier_id) && ` · ${suppliers.get(c.supplier_id).name}`}
                      {c.receipt_name && ` · ${t("costs.hasReceipt")}`}
                    </span>
                  </span>
                  <PaidBadge status={c.status} due={c.due_date} />
                  <span className="w-28 shrink-0 text-right font-semibold tabular-nums text-zinc-900">{formatMoney(c.amount)}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="flex justify-end gap-6 border-t border-zinc-100 px-4 py-3 text-sm">
            <span className="text-zinc-500">
              {t("costs.paid")}: <span className="font-semibold tabular-nums text-zinc-900">{formatMoney(costs.data.total_paid)}</span>
            </span>
            <span className="text-zinc-500">
              {t("costs.toPay")}: <span className="font-semibold tabular-nums text-zinc-900">{formatMoney(costs.data.total_due)}</span>
            </span>
          </p>
        </section>
      )}

      <p className="mt-6 text-xs text-zinc-500">{t("costs.notAccounting")}</p>

      <CostSheet open={sheet?.kind === "cost"} cost={sheet?.kind === "cost" ? sheet.item : null} onClose={() => setSheet(null)} />
      <RecurringSheet open={sheet?.kind === "recurring"} schedule={sheet?.kind === "recurring" ? sheet.item : null} onClose={() => setSheet(null)} />
    </>
  );
}

/** On a sent or received purchase order: record it once as a cost. */
export function PurchaseOrderCost({ po }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const allowed = ["admin", "manager"].includes(user?.role) && ["sent", "received"].includes(po.status);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ category: "stock", paid: true, paid_date: todayIso() });
  const { data: recorded, isLoading } = useQuery({ queryKey: ["costs", "po", po.id], queryFn: () => get(`/costs/from-purchase-order/${po.id}`), enabled: allowed });
  const record = useMutation({
    mutationFn: () => apiClient.post(`/costs/from-purchase-order/${po.id}`, { category: form.category.trim(), paid: form.paid, paid_date: form.paid ? form.paid_date : null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["costs"] });
      toast.success(t("costs.poRecorded"));
      setOpen(false);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  if (!allowed || isLoading) return null;
  if (recorded)
    return (
      <Link to="/costs" className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50">
        ✓ {t("costs.poAlready")}
      </Link>
    );
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        {t("costs.recordPo")}
      </Button>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title={t("costs.recordPo")}
        footer={
          <Button disabled={record.isPending || !form.category.trim()} onClick={() => record.mutate()}>
            {t("costs.recordPo")}
          </Button>
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-zinc-600">{t("costs.recordPoHint", { number: po.po_number, amount: formatMoney(po.total) })}</p>
          <Field label={t("costs.categoryLabel")}>
            <CategoryPicker value={form.category} onChange={(category) => setForm((f) => ({ ...f, category }))} />
          </Field>
          <FilterChips
            bare
            label={t("costs.paidQuestion")}
            options={[
              { value: true, label: t("costs.alreadyPaid") },
              { value: false, label: t("costs.payLater") },
            ]}
            value={form.paid}
            onChange={(paid) => setForm((f) => ({ ...f, paid }))}
          />
          {form.paid && (
            <Field label={t("costs.paidOn")}>
              <input className="input" type="date" value={form.paid_date} onChange={(e) => setForm((f) => ({ ...f, paid_date: e.target.value }))} />
            </Field>
          )}
        </div>
      </Sheet>
    </>
  );
}
