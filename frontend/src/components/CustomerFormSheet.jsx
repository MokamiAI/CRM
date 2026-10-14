import { useCustomer } from "../hooks/useApi";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import Sheet from "./Sheet";
import { Button, Field } from "./ui";
import { CustomFieldInputs, toFormValues } from "./CustomFields";
import { errorMessage } from "../utils/format";

const EMPTY = { name: "", email: "", phone: "", billing_address: "", tax_number: "", notes: "" };

function nullsToEmpty(obj) {
  return Object.fromEntries(Object.keys(EMPTY).map((k) => [k, obj[k] ?? ""]));
}

// Blank optional fields go to the API as null, not "", so e.g. an emptied
// email clears the address instead of failing email validation.
function emptyToNull(obj) {
  return Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, v === "" ? null : v]));
}

/** Create (customer = null) or edit a customer. */
/** Edit a customer by id: loads the whole record first, so no field is lost. */
export function EditCustomerSheet({ id, onClose }) {
  const { data: customer } = useCustomer(id);
  return <CustomerFormSheet open={Boolean(customer)} onClose={onClose} customer={customer ?? null} />;
}

export default function CustomerFormSheet({ open, onClose, customer, onSaved }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canDeactivate = ["admin", "manager"].includes(user?.role);
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [custom, setCustom] = useState({});
  const [marketing, setMarketing] = useState(true);

  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setForm(customer ? nullsToEmpty(customer) : EMPTY);
      setCustom(toFormValues(customer?.custom_fields));
      setMarketing(!customer?.marketing_opt_out);
    }
  }

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["customers"] });
    if (customer) queryClient.invalidateQueries({ queryKey: ["customer", customer.id] });
  };

  const save = useMutation({
    mutationFn: (payload) =>
      (customer ? apiClient.patch(`/customers/${customer.id}`, payload) : apiClient.post("/customers", payload)).then((r) => r.data),
    onSuccess: (saved) => {
      toast.success(t(customer ? "customerForm.updated" : "customerForm.added"));
      refresh();
      onClose();
      onSaved?.(saved);
    },
    onError: (error) => toast.error(errorMessage(error, t("customerForm.saveFailed"))),
  });

  const deactivate = useMutation({
    mutationFn: () => apiClient.post(`/customers/${customer.id}/deactivate`),
    onSuccess: () => {
      toast.success(t("customerForm.deactivated"));
      refresh();
      onClose();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const update = (field) => (event) => setForm((prev) => ({ ...prev, [field]: event.target.value }));

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t(customer ? "customerForm.editTitle" : "customerForm.newTitle")}
      footer={
        <>
          {customer?.is_active && canDeactivate && (
            <Button variant="danger" className="mr-auto" disabled={deactivate.isPending} onClick={() => deactivate.mutate()}>
              {t("customerForm.deactivate")}
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="customer-form" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? t("common.saving") : t("common.save")}
          </button>
        </>
      }
    >
      <form
        id="customer-form"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate({ ...emptyToNull(form), custom_fields: custom, ...(customer && { marketing_opt_out: !marketing }) });
        }}
        className="space-y-4"
      >
        <Field label={t("customerForm.name")}>
          <input className="input" required value={form.name} onChange={update("name")} />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={t("customerForm.email")} hint={t("customerForm.emailHint")}>
            <input className="input" type="email" autoCapitalize="none" autoCorrect="off" value={form.email} onChange={update("email")} />
          </Field>
          <Field label={t("customerForm.phone")}>
            <input className="input" type="tel" value={form.phone} onChange={update("phone")} />
          </Field>
        </div>
        <Field label={t("customerForm.address")}>
          <textarea className="input" rows={3} value={form.billing_address} onChange={update("billing_address")} />
        </Field>
        <Field label={t("customerForm.taxNumber")}>
          <input className="input" value={form.tax_number} onChange={update("tax_number")} />
        </Field>
        <Field label={t("customerForm.background")} hint={t("customerForm.backgroundHint")}>
          <textarea className="input" rows={2} value={form.notes} onChange={update("notes")} />
        </Field>
        <CustomFieldInputs entity="customer" values={custom} onChange={setCustom} />
        {customer && (
          <label className="flex items-start gap-3 border-t border-zinc-100 pt-4 text-sm">
            <input type="checkbox" className="mt-0.5 h-4 w-4" checked={marketing} onChange={(e) => setMarketing(e.target.checked)} />
            <span>
              <span className="font-medium text-zinc-900">{t("customerForm.marketing")}</span>
              <span className="block text-xs text-zinc-500">{t("customerForm.marketingHint")}</span>
            </span>
          </label>
        )}
      </form>
    </Sheet>
  );
}
