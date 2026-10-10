import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useCustomFields } from "../hooks/useApi";
import { errorMessage } from "../utils/format";
import { Button, FilterChips } from "./ui";

const TYPES = ["text", "number", "date", "select", "boolean"];
const BLANK = { label: "", field_type: "text", options: "", required: false };

const splitOptions = (text) =>
  text
    .split(",")
    .map((o) => o.trim())
    .filter(Boolean);

/** Admin settings card: define the extra fields shown on customers and deals.
 *  Each change saves straight away (it sits outside the main settings form). */
export default function CustomFieldsManager() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [entity, setEntity] = useState("customer");
  const { data: fields = [], isLoading } = useCustomFields(entity);
  const [draft, setDraft] = useState(BLANK);
  const [editing, setEditing] = useState(null); // { id, label, options, required }
  const [confirming, setConfirming] = useState(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["custom-fields"] });
  const onError = (error) => toast.error(errorMessage(error));

  const create = useMutation({
    mutationFn: (body) => apiClient.post("/custom-fields", body),
    onSuccess: () => {
      refresh();
      setDraft(BLANK);
      toast.success(t("customFields.added"));
    },
    onError,
  });
  const update = useMutation({
    mutationFn: ({ id, ...body }) => apiClient.patch(`/custom-fields/${id}`, body),
    onSuccess: (_r, vars) => {
      refresh();
      setEditing(null);
      if (vars.position === undefined) toast.success(t("customFields.updated"));
    },
    onError,
  });
  const remove = useMutation({
    mutationFn: (id) => apiClient.delete(`/custom-fields/${id}`),
    onSuccess: () => {
      refresh();
      setConfirming(null);
      toast.success(t("customFields.removed"));
    },
    onError,
  });

  // Swap positions with the neighbour; renumber so gaps never confuse order.
  const move = (index, delta) => {
    const order = [...fields];
    const [item] = order.splice(index, 1);
    order.splice(index + delta, 0, item);
    order.forEach((f, position) => {
      if (f.position !== position) update.mutate({ id: f.id, position });
    });
  };

  const add = () => {
    if (!draft.label.trim()) return;
    create.mutate({
      entity,
      label: draft.label,
      field_type: draft.field_type,
      options: draft.field_type === "select" ? splitOptions(draft.options) : [],
      required: draft.required,
    });
  };

  const typeLabel = (type) => t(`customFields.types.${type}`);

  return (
    <section className="card p-4 sm:p-6">
      <h2 className="mb-1 text-base font-semibold text-zinc-900">{t("customFields.title")}</h2>
      <p className="mb-4 text-sm text-zinc-500">{t("customFields.intro")}</p>
      <FilterChips
        value={entity}
        onChange={(value) => {
          setEntity(value);
          setEditing(null);
          setConfirming(null);
        }}
        options={[
          { value: "customer", label: t("nav.customers") },
          { value: "deal", label: t("nav.deals") },
        ]}
      />

      <ul className="divide-y divide-zinc-100 rounded-lg border border-zinc-200/80">
        {!isLoading && fields.length === 0 && <li className="px-4 py-3 text-sm text-zinc-500">{t("customFields.none")}</li>}
        {fields.map((field, index) =>
          editing?.id === field.id ? (
            <li key={field.id} className="space-y-3 bg-zinc-50/60 px-4 py-3">
              <input
                className="input"
                aria-label={t("customFields.label")}
                value={editing.label}
                onChange={(e) => setEditing({ ...editing, label: e.target.value })}
              />
              {field.field_type === "select" && (
                <input
                  className="input"
                  aria-label={t("customFields.options")}
                  value={editing.options}
                  onChange={(e) => setEditing({ ...editing, options: e.target.value })}
                />
              )}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label className="flex items-center gap-2 text-sm text-zinc-700">
                  <input
                    type="checkbox"
                    className="h-4 w-4"
                    checked={editing.required}
                    onChange={(e) => setEditing({ ...editing, required: e.target.checked })}
                  />
                  {t("customFields.required")}
                </label>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => setEditing(null)}>
                    {t("common.cancel")}
                  </Button>
                  <Button
                    disabled={update.isPending || !editing.label.trim()}
                    onClick={() =>
                      update.mutate({
                        id: field.id,
                        label: editing.label,
                        required: editing.required,
                        ...(field.field_type === "select" && { options: splitOptions(editing.options) }),
                      })
                    }
                  >
                    {t("common.save")}
                  </Button>
                </div>
              </div>
            </li>
          ) : (
            <li key={field.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-zinc-900">
                  {field.label}
                  {field.required && <span className="ml-1.5 text-xs font-normal text-rose-600">{t("customFields.required")}</span>}
                </p>
                <p className="truncate text-xs text-zinc-500">
                  {typeLabel(field.field_type)}
                  {field.options.length > 0 && ` · ${field.options.join(", ")}`}
                </p>
              </div>
              {confirming === field.id ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-zinc-600">{t("customFields.confirmDelete")}</span>
                  <Button variant="secondary" className="!h-8 !px-2.5 !text-xs" onClick={() => setConfirming(null)}>
                    {t("common.cancel")}
                  </Button>
                  <Button variant="danger" className="!h-8 !px-2.5 !text-xs" disabled={remove.isPending} onClick={() => remove.mutate(field.id)}>
                    {t("common.delete")}
                  </Button>
                </div>
              ) : (
                <div className="flex items-center gap-1">
                  <IconButton label={t("customFields.moveUp")} disabled={index === 0} onClick={() => move(index, -1)}>
                    ↑
                  </IconButton>
                  <IconButton label={t("customFields.moveDown")} disabled={index === fields.length - 1} onClick={() => move(index, 1)}>
                    ↓
                  </IconButton>
                  <Button
                    variant="secondary"
                    className="!h-8 !px-2.5 !text-xs"
                    onClick={() =>
                      setEditing({ id: field.id, label: field.label, options: field.options.join(", "), required: field.required })
                    }
                  >
                    {t("common.edit")}
                  </Button>
                  <Button variant="secondary" className="!h-8 !px-2.5 !text-xs" onClick={() => setConfirming(field.id)}>
                    {t("common.delete")}
                  </Button>
                </div>
              )}
            </li>
          )
        )}
      </ul>

      <div
        className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-[1fr_10rem]"
        onKeyDown={(e) => {
          if (e.key === "Enter" && e.target.tagName === "INPUT" && e.target.type !== "checkbox") {
            e.preventDefault();
            add();
          }
        }}
      >
        <label className="block">
          <span className="label">{t("customFields.label")}</span>
          <input className="input" value={draft.label} maxLength={100} onChange={(e) => setDraft({ ...draft, label: e.target.value })} />
        </label>
        <label className="block">
          <span className="label">{t("customFields.type")}</span>
          <select className="input" value={draft.field_type} onChange={(e) => setDraft({ ...draft, field_type: e.target.value })}>
            {TYPES.map((type) => (
              <option key={type} value={type}>
                {typeLabel(type)}
              </option>
            ))}
          </select>
        </label>
        {draft.field_type === "select" && (
          <label className="block sm:col-span-2">
            <span className="label">{t("customFields.options")}</span>
            <input className="input" value={draft.options} onChange={(e) => setDraft({ ...draft, options: e.target.value })} />
            <span className="mt-1.5 block text-xs text-zinc-500">{t("customFields.optionsHint")}</span>
          </label>
        )}
        <div className="flex items-center justify-between gap-3 sm:col-span-2">
          <label className="flex items-center gap-2 text-sm text-zinc-700">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={draft.required}
              onChange={(e) => setDraft({ ...draft, required: e.target.checked })}
            />
            {t("customFields.required")}
          </label>
          <Button
            disabled={
              create.isPending || !draft.label.trim() || (draft.field_type === "select" && splitOptions(draft.options).length === 0)
            }
            onClick={add}
          >
            {t("customFields.add")}
          </Button>
        </div>
      </div>
    </section>
  );
}

function IconButton({ label, children, ...props }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="pressable grid h-8 w-8 place-items-center rounded-md text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-30"
      {...props}
    >
      {children}
    </button>
  );
}
