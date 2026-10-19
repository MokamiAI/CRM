import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useContacts, usePipelineAccounts, useTeam } from "../hooks/useApi";
import Sheet from "./Sheet";
import { Button, Field } from "./ui";
import PartyCombobox from "./PartyCombobox";
import { PRIORITIES, STAGES, industryFromCustomer, industryOptions } from "./crm";
import { CustomFieldInputs, toFormValues } from "./CustomFields";
import { CURRENCY, errorMessage } from "../utils/format";

// The chosen priority button, in its own colour.
const SELECTED = {
  high: "bg-red-50 text-red-800 ring-red-400",
  medium: "bg-amber-50 text-amber-900 ring-amber-400",
  low: "bg-zinc-100 text-zinc-800 ring-zinc-400",
};

const blank = (customerId) => ({
  title: "",
  customer_id: customerId ?? "",
  customer_name: "", // typed; a new customer is added on save
  contact_id: "",
  owner_id: "",
  stage: "lead",
  priority: "medium",
  value: "",
  expected_close_date: "",
  industry: "",
  mcem_enabled: false,
});

/** Create a deal (deal = null), optionally pre-linked to a customer, or edit one. */
export default function DealFormSheet({ open, onClose, deal, customerId, initialStage, onSaved }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(blank(customerId));
  const [custom, setCustom] = useState({});
  const [person, setPerson] = useState(null);
  const { data: customers = [] } = usePipelineAccounts();
  const { data: contacts = [], isLoading: contactsLoading, isError: contactsError } = useContacts(form.customer_id || null);
  const { data: team = [] } = useTeam();
  // A customer chosen up front (from a customer's page): show its name.
  useEffect(() => {
    if (!form.customer_id || form.customer_name) return;
    const known = customers.find((c) => c.id === form.customer_id);
    if (known) setForm((prev) => ({ ...prev, customer_name: known.name }));
  }, [customers, form.customer_id, form.customer_name]);

  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setPerson(null);
      setCustom(toFormValues(deal?.custom_fields));
      setForm(
        deal
          ? {
              title: deal.title,
              customer_id: deal.customer_id,
              contact_id: deal.contact_id ?? "",
              owner_id: deal.owner_id ?? "",
              stage: deal.stage,
              priority: deal.priority ?? "medium",
              value: String(Number(deal.value)),
              expected_close_date: deal.expected_close_date ?? "",
              industry: deal.industry ?? "",
            }
          : {
              ...blank(customerId),
              stage: "lead",
              industry: industryFromCustomer(customers.find((c) => c.id === customerId)),
            }
      );
    }
  }

  // Edit the deal's person directly; new deals start with the customer's
  // primary person, if one exists. Refetches must not overwrite typing.
  useEffect(() => {
    if (!open || person || contactsLoading || contactsError) return;
    const contact = form.customer_id
      ? (deal?.contact_id ? contacts.find(c => c.id === deal.contact_id) : contacts.find(c => c.is_primary) || contacts[0])
      : null;
    setPerson({
      id: contact?.id || null,
      name: [contact?.first_name, contact?.last_name].filter(Boolean).join(" "),
      email: contact?.email || "",
      phone: contact?.phone || "",
      job_title: contact?.job_title || "",
    });
  }, [open, person, contactsLoading, contactsError, contacts, form.customer_id, deal?.contact_id]);

  const save = useMutation({
    mutationFn: async () => {
      // A new name typed in: add the customer first, then the deal.
      let customerIdToUse = form.customer_id;
      if (!deal && !customerIdToUse) {
        const { data: made } = await apiClient.post("/prospects", { name: form.customer_name.trim() });
        customerIdToUse = made.id;
        setForm((prev) => ({ ...prev, customer_id: made.id, customer_name: made.name }));
        queryClient.invalidateQueries({ queryKey: ["pipeline-accounts"] });
        toast.success(t("party.added.prospect", { name: made.name }));
      }
      let contactId = person?.id || null;
      if (person?.name.trim()) {
        const [first_name, ...last] = person.name.trim().split(/\s+/);
        const details = {
          first_name, last_name: last.join(" ") || null,
          email: person.email.trim() || null,
          phone: person.phone.trim() || null,
          job_title: person.job_title.trim() || null,
        };
        const { data: savedPerson } = contactId
          ? await apiClient.patch(`/contacts/${contactId}`, details)
          : await apiClient.post(`/customers/${customerIdToUse}/contacts`, details);
        contactId = savedPerson.id;
        setPerson(prev => ({ ...prev, id: contactId }));
        queryClient.invalidateQueries({ queryKey: ["contacts"] });
      }
      const payload = {
        title: form.title,
        contact_id: contactId,
        owner_id: form.owner_id || null,
        value: form.value || "0",
        expected_close_date: form.expected_close_date || null,
        industry: form.industry || null,
        priority: form.priority,
        custom_fields: custom,
      };
      return deal
        ? apiClient.patch(`/deals/${deal.id}`, payload).then((r) => r.data)
        : apiClient.post("/deals", { ...payload, customer_id: customerIdToUse, stage: form.stage, mcem_enabled: form.mcem_enabled }).then((r) => r.data);
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["deals"] });
      queryClient.invalidateQueries({ queryKey: ["customers"] });
    queryClient.invalidateQueries({ queryKey: ["pipeline-accounts"] });
    queryClient.invalidateQueries({ queryKey: ["quote"] });
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      queryClient.invalidateQueries({ queryKey: ["deal", saved.id] });
      queryClient.invalidateQueries({ queryKey: ["timeline"] });
      toast.success(t(deal ? "dealForm.updated" : "dealForm.created"));
      onClose();
      onSaved?.(saved);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const set = (field) => (event) =>
    setForm((prev) => {
      const next = { ...prev, [field]: event.target.value };
      if (field === "customer_id") {
        next.contact_id = "";
        if (!prev.industry) next.industry = industryFromCustomer(customers.find((c) => c.id === event.target.value));
      }
      return next;
    });

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t(deal ? "dealForm.editTitle" : "dealForm.newTitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="deal-form" className="btn btn-primary" disabled={save.isPending || contactsLoading || contactsError || !person}>
            {save.isPending ? t("common.saving") : deal ? t("common.save") : t("dealForm.create")}
          </button>
        </>
      }
    >
      <form
        id="deal-form"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
        className="space-y-4"
      >
        <Field label={t("dealForm.name")} hint={t("dealForm.nameHint")}>
          <input className="input" required value={form.title} onChange={set("title")} />
        </Field>
        {!deal && (
          <Field label={t("dealForm.account")}>
            <PartyCombobox
              parties={customers}
              value={{ id: form.customer_id || null, name: form.customer_name }}
              onChange={({ id, name }) => {
                if (id !== (form.customer_id || null)) setPerson(null);
                setForm((prev) => ({
                  ...prev,
                  customer_id: id ?? "",
                  customer_name: name,
                  contact_id: id === (prev.customer_id || null) ? prev.contact_id : "",
                  industry: prev.industry || (id ? industryFromCustomer(customers.find((c) => c.id === id)) : ""),
                }));
              }}
              kind="prospect"
              required
              disabled={Boolean(customerId)}
              placeholder={t("party.typeProspect")}
            />
          </Field>
        )}
        <fieldset className="space-y-3" disabled={contactsLoading || contactsError || !person}>
          <legend className="mb-1.5 block text-sm font-medium text-zinc-700">{t("dealForm.contact")}</legend>
          {contactsError && <p role="alert" className="text-sm text-red-700">{t("dealForm.contactLoadError")}</p>}
          <Field label={t("customerForm.contactName")}>
            <input className="input" autoComplete="name" maxLength={241}
              required={Boolean(person?.id || person?.email || person?.phone || person?.job_title)}
              value={person?.name || ""} onChange={e => setPerson(p => ({ ...p, name: e.target.value }))} />
          </Field>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={t("login.email")}>
              <input className="input" type="email" autoComplete="email" maxLength={255} value={person?.email || ""}
                onChange={e => setPerson(p => ({ ...p, email: e.target.value }))} />
            </Field>
            <Field label={t("customerForm.phone")}>
              <input className="input" type="tel" autoComplete="tel" maxLength={50} value={person?.phone || ""}
                onChange={e => setPerson(p => ({ ...p, phone: e.target.value }))} />
            </Field>
          </div>
          <Field label={t("contact.jobTitle")}>
            <input className="input" autoComplete="organization-title" maxLength={120} value={person?.job_title || ""}
              onChange={e => setPerson(p => ({ ...p, job_title: e.target.value }))} />
          </Field>
        </fieldset>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("dealForm.value", { currency: CURRENCY })}>
            <input className="input tabular-nums" inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={form.value} onChange={set("value")} placeholder="0" />
          </Field>
          <Field label={t("dealForm.expectedClose")}>
            <input className="input" type="date" value={form.expected_close_date} onChange={set("expected_close_date")} />
          </Field>
        </div>
        <Field label={t("dealForm.industry")}>
          <select className="input" value={form.industry} onChange={set("industry")}>
            <option value="">{t("dealForm.noIndustry")}</option>
            {industryOptions().map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
        {!deal && !form.mcem_enabled && (
          // Four stages as buttons, not a dropdown: always all visible (a
          // native list near the bottom of the sheet opened off-screen).
          <fieldset>
            <legend className="mb-1.5 block text-sm font-medium text-zinc-700">{t("dealForm.stage")}</legend>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {STAGES.map((s) => (
                <label
                  key={s.value}
                  className={`flex min-h-11 cursor-pointer items-center justify-center rounded-lg px-2 text-center text-sm font-medium ring-1 ring-inset transition-colors duration-150 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-indigo-500 ${
                    form.stage === s.value ? "bg-indigo-50 text-indigo-800 ring-indigo-500" : "bg-white text-zinc-700 ring-zinc-200 hover:bg-zinc-50"
                  }`}
                >
                  <input type="radio" name="deal-stage" value={s.value} disabled={form.mcem_enabled && s.value !== "lead"} checked={form.stage === s.value} onChange={set("stage")} className="sr-only" />
                  {s.label}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        {!deal && <div className="space-y-1"><label className="flex min-h-11 items-center gap-2 text-sm font-bold text-zinc-900"><input type="checkbox" checked={form.mcem_enabled} onChange={e => setForm(p => ({ ...p, mcem_enabled: e.target.checked, ...(e.target.checked ? { stage: "lead" } : {}) }))} />Use the advanced pipeline (Milestones)</label><p className="text-xs text-zinc-500">Start in Listen and Consult. Confirm customer evidence before advancing; delivery and value reviews continue after Won.</p></div>}
        <fieldset>
          <legend className="mb-1.5 block text-sm font-medium text-zinc-700">{t("priority.label")}</legend>
          <div className="grid grid-cols-3 gap-2">
            {PRIORITIES.map((p) => (
              <label
                key={p}
                className={`flex min-h-11 cursor-pointer items-center justify-center rounded-lg px-2 text-sm font-medium ring-1 ring-inset transition-colors duration-150 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-indigo-500 ${
                  form.priority === p ? SELECTED[p] : "bg-white text-zinc-700 ring-zinc-200 hover:bg-zinc-50"
                }`}
              >
                <input type="radio" name="deal-priority" value={p} checked={form.priority === p} onChange={set("priority")} className="sr-only" />
                {t(`priority.${p}`)}
              </label>
            ))}
          </div>
          <p className="mt-1.5 text-xs text-zinc-500">{t("priority.hint")}</p>
        </fieldset>
        {team.length > 1 && (
          <Field label={t("dealForm.owner")}>
            <select className="input" value={form.owner_id} onChange={set("owner_id")}>
              <option value="">{t(deal ? "dealForm.unassigned" : "composer.me")}</option>
              {team.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
            </select>
          </Field>
        )}
        <CustomFieldInputs entity="deal" values={custom} onChange={setCustom} />
      </form>
    </Sheet>
  );
}
