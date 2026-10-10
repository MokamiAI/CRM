import { useTranslation } from "react-i18next";
import { useCustomFields } from "../hooks/useApi";
import i18n from "../i18n";
import { intlLocale } from "../i18n/languages";
import { formatDate } from "../utils/format";
import { Field } from "./ui";

// Values travel as strings in the form (inputs are controlled text) and the
// server coerces them to the field's type, so "" always means "clear".
export function toFormValues(values = {}) {
  return Object.fromEntries(
    Object.entries(values ?? {}).map(([key, value]) => [key, typeof value === "boolean" ? String(value) : String(value ?? "")])
  );
}

/** Inputs for the admin-defined fields of a customer or deal. */
export function CustomFieldInputs({ entity, values, onChange }) {
  const { t } = useTranslation();
  const { data: fields = [] } = useCustomFields(entity);
  if (!fields.length) return null;

  const set = (key) => (event) => onChange({ ...values, [key]: event.target.value });

  return (
    <div className="space-y-4 border-t border-zinc-100 pt-4">
      {fields.map((field) => {
        const value = values[field.key] ?? "";
        const label = field.required ? `${field.label} *` : field.label;
        if (field.field_type === "select" || field.field_type === "boolean") {
          const options =
            field.field_type === "select"
              ? field.options.map((o) => [o, o])
              : [
                  ["true", t("customFields.yes")],
                  ["false", t("customFields.no")],
                ];
          return (
            <Field key={field.id} label={label}>
              <select className="input" required={field.required} value={value} onChange={set(field.key)}>
                <option value="">{t("customFields.choose")}</option>
                {options.map(([v, text]) => (
                  <option key={v} value={v}>
                    {text}
                  </option>
                ))}
              </select>
            </Field>
          );
        }
        return (
          <Field key={field.id} label={label}>
            <input
              className={`input ${field.field_type === "number" ? "tabular-nums" : ""}`}
              type={field.field_type === "date" ? "date" : "text"}
              inputMode={field.field_type === "number" ? "decimal" : undefined}
              required={field.required}
              value={value}
              onChange={set(field.key)}
            />
          </Field>
        );
      })}
    </div>
  );
}

function display(field, value, t) {
  if (field.field_type === "boolean") return t(value ? "customFields.yes" : "customFields.no");
  if (field.field_type === "date") return formatDate(value);
  if (field.field_type === "number") return Number(value).toLocaleString(intlLocale(i18n.language));
  return String(value);
}

/** [label, displayValue] rows for a record's filled-in custom fields, to
 *  append to a detail card's own rows. */
export function useCustomFieldRows(entity, values) {
  const { t } = useTranslation();
  const { data: fields = [] } = useCustomFields(entity);
  return fields
    .filter((f) => values?.[f.key] !== undefined && values?.[f.key] !== "")
    .map((f) => [f.label, display(f, values[f.key], t)]);
}
