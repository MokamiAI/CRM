import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import Sheet from "./Sheet";
import { Button, Field } from "./ui";
import { errorMessage } from "../utils/format";

export const EMPTY_SUPPLIER = { name: "", contact_name: "", email: "", phone: "", tax_number: "", address: "", notes: "" };

/** Add (supplier without an id, e.g. { name } typed on a PO) or edit a
 *  supplier. `onSaved` gets the saved supplier. */
export default function SupplierSheet({ supplier, onClose, onSaved }) {
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
  const done = (message, saved) => {
    queryClient.invalidateQueries({ queryKey: ["suppliers"] });
    toast.success(message);
    onClose();
    if (saved) onSaved?.(saved);
  };
  const save = useMutation({
    mutationFn: () => (isNew ? apiClient.post("/suppliers", form) : apiClient.patch(`/suppliers/${supplier.id}`, form)).then((r) => r.data),
    onSuccess: (saved) => done(t("suppliers.saved"), saved),
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
