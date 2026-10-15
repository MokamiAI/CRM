import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useContacts, useCustomers, useTeam } from "../hooks/useApi";
import Sheet from "./Sheet";
import { Button, Field } from "./ui";
import { STAGES, industryFromCustomer, industryOptions } from "./crm";
import { CustomFieldInputs, toFormValues } from "./CustomFields";
import { CURRENCY, errorMessage } from "../utils/format";

const blank = (customerId) => ({
  title: "",
  customer_id: customerId ?? "",
  contact_id: "",
  owner_id: "",
  stage: "lead",
  value: "",
  expected_close_date: "",
  industry: "",
});

/** Create a deal (deal = null), optionally pre-linked to a customer, or edit one. */
export default function DealFormSheet({ open, onClose, deal, customerId, initialStage, onSaved }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(blank(customerId));
  const [custom, setCustom] = useState({});
  const { data: customers = [] } = useCustomers({ is_active: true });
  const { data: contacts = [] } = useContacts(form.customer_id || null);
  const { data: team = [] } = useTeam();

  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setCustom(toFormValues(deal?.custom_fields));
      setForm(
        deal
          ? {
              title: deal.title,
              customer_id: deal.customer_id,
              contact_id: deal.contact_id ?? "",
              owner_id: deal.owner_id ?? "",
              stage: deal.stage,
              value: String(Number(deal.value)),
              expected_close_date: deal.expected_close_date ?? "",
              industry: deal.industry ?? "",
            }
          : {
              ...blank(customerId),
              stage: initialStage ?? "lead",
              industry: industryFromCustomer(customers.find((c) => c.id === customerId)),
            }
      );
    }
  }

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        title: form.title,
        contact_id: form.contact_id || null,
        owner_id: form.owner_id || null,
        value: form.value || "0",
        expected_close_date: form.expected_close_date || null,
        industry: form.industry || null,
        custom_fields: custom,
      };
      return deal
        ? apiClient.patch(`/deals/${deal.id}`, payload).then((r) => r.data)
        : apiClient.post("/deals", { ...payload, customer_id: form.customer_id, stage: form.stage }).then((r) => r.data);
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["deals"] });
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
          <button type="submit" form="deal-form" className="btn btn-primary" disabled={save.isPending}>
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
          <Field label={t("dealForm.customer")}>
            <select className="input" required value={form.customer_id} onChange={set("customer_id")} disabled={Boolean(customerId)}>
              <option value="" disabled>
                {t("dealForm.chooseCustomer")}
              </option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label={t("dealForm.contact")}>
          <select className="input" value={form.contact_id} onChange={set("contact_id")} disabled={!form.customer_id}>
            <option value="">{t(contacts.length ? "dealForm.noOne" : "dealForm.noContacts")}</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {[c.first_name, c.last_name].filter(Boolean).join(" ")}
                {c.job_title ? ` · ${c.job_title}` : ""}
              </option>
            ))}
          </select>
        </Field>
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
        {!deal && (
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
                  <input type="radio" name="deal-stage" value={s.value} checked={form.stage === s.value} onChange={set("stage")} className="sr-only" />
                  {s.label}
                </label>
              ))}
            </div>
          </fieldset>
        )}
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
