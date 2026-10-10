import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useAudience, useCustomFields } from "../hooks/useApi";
import { errorMessage } from "../utils/format";
import Sheet from "./Sheet";
import { Button, Field } from "./ui";

// The rule kinds the audience builder offers. The API stores yes/no rules
// as one kind with a value, but people think of them as separate choices.
const CHOICES = [
  { id: "has_open_deal", rule: { kind: "has_open_deal", value: true } },
  { id: "no_open_deal", rule: { kind: "has_open_deal", value: false } },
  { id: "has_open_balance", rule: { kind: "has_open_balance", value: true } },
  { id: "no_open_balance", rule: { kind: "has_open_balance", value: false } },
  { id: "bought_within_days", rule: { kind: "bought_within_days", days: 90 } },
  { id: "no_purchase_days", rule: { kind: "no_purchase_days", days: 90 } },
  { id: "created_within_days", rule: { kind: "created_within_days", days: 30 } },
  { id: "custom_field", rule: { kind: "custom_field", key: "", value: "" } },
];

function choiceOf(rule) {
  if (rule.kind === "has_open_deal") return rule.value ? "has_open_deal" : "no_open_deal";
  if (rule.kind === "has_open_balance") return rule.value ? "has_open_balance" : "no_open_balance";
  return rule.kind;
}

// Custom-field rules without a field or value would match nobody; leave
// them out until they're filled in.
export const completeRules = (rules) => rules.filter((r) => r.kind !== "custom_field" || (r.key && r.value !== ""));

/** One-line, human description of a rule ("Hasn't bought in 90 days"). */
export function useRuleText() {
  const { t } = useTranslation();
  const { data: fields = [] } = useCustomFields("customer");
  return (rule) => {
    const choice = choiceOf(rule);
    if (choice === "custom_field") {
      const field = fields.find((f) => f.key === rule.key);
      const value = field?.field_type === "boolean" ? t(rule.value === "true" ? "customFields.yes" : "customFields.no") : rule.value;
      return t("marketing.rule.customText", { field: field?.label ?? rule.key, value });
    }
    return t(`marketing.rule.${choice}Text`, { count: rule.days });
  };
}

function RuleRow({ rule, onChange, onRemove }) {
  const { t } = useTranslation();
  const { data: fields = [] } = useCustomFields("customer");
  const choice = choiceOf(rule);
  const field = fields.find((f) => f.key === rule.key);

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg bg-zinc-50 p-2.5 ring-1 ring-zinc-200/70">
      <select
        className="input !h-9 min-w-0 flex-1 !py-1 !text-sm"
        aria-label={t("marketing.rule.label")}
        value={choice}
        onChange={(e) => onChange({ ...CHOICES.find((c) => c.id === e.target.value).rule })}
      >
        {CHOICES.filter((c) => c.id !== "custom_field" || fields.length).map((c) => (
          <option key={c.id} value={c.id}>
            {t(`marketing.rule.${c.id}`)}
          </option>
        ))}
      </select>
      {"days" in rule && (
        <label className="flex items-center gap-1.5 text-sm text-zinc-600">
          <input
            className="input !h-9 w-20 !py-1 !text-sm tabular-nums"
            type="number"
            min={1}
            max={3650}
            value={rule.days}
            onChange={(e) => onChange({ ...rule, days: Math.max(1, Number(e.target.value) || 1) })}
          />
          {t("marketing.rule.days")}
        </label>
      )}
      {choice === "custom_field" && (
        <>
          <select
            className="input !h-9 w-40 !py-1 !text-sm"
            aria-label={t("customFields.label")}
            value={rule.key}
            onChange={(e) => onChange({ ...rule, key: e.target.value, value: "" })}
          >
            <option value="">{t("customFields.choose")}</option>
            {fields.map((f) => (
              <option key={f.id} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
          {field?.field_type === "select" || field?.field_type === "boolean" ? (
            <select
              className="input !h-9 w-40 !py-1 !text-sm"
              aria-label={t("marketing.rule.value")}
              value={rule.value}
              onChange={(e) => onChange({ ...rule, value: e.target.value })}
            >
              <option value="">{t("customFields.choose")}</option>
              {(field.field_type === "select"
                ? field.options.map((o) => [o, o])
                : [
                    ["true", t("customFields.yes")],
                    ["false", t("customFields.no")],
                  ]
              ).map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="input !h-9 w-40 !py-1 !text-sm"
              aria-label={t("marketing.rule.value")}
              value={rule.value}
              disabled={!rule.key}
              onChange={(e) => onChange({ ...rule, value: e.target.value })}
            />
          )}
        </>
      )}
      <button
        type="button"
        onClick={onRemove}
        aria-label={t("marketing.rule.remove")}
        className="pressable grid h-8 w-8 place-items-center rounded-md text-zinc-400 hover:bg-zinc-200/60 hover:text-zinc-700"
      >
        ×
      </button>
    </div>
  );
}

/** Edit a list of rules, with the live count of who matches. */
export function RulesEditor({ rules, onChange }) {
  const { t } = useTranslation();
  const { data: audience, isFetching } = useAudience(completeRules(rules));
  return (
    <div className="space-y-2">
      {rules.length === 0 && <p className="text-sm text-zinc-500">{t("marketing.rule.everyone")}</p>}
      {rules.map((rule, i) => (
        <RuleRow
          key={i}
          rule={rule}
          onChange={(next) => onChange(rules.map((r, j) => (j === i ? next : r)))}
          onRemove={() => onChange(rules.filter((_, j) => j !== i))}
        />
      ))}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <Button variant="secondary" className="!h-8 !px-2.5 !text-xs" onClick={() => onChange([...rules, { ...CHOICES[0].rule }])}>
          + {t("marketing.rule.add")}
        </Button>
        <AudienceCount audience={audience} loading={isFetching} />
      </div>
    </div>
  );
}

export function AudienceCount({ audience, loading }) {
  const { t } = useTranslation();
  if (!audience) return null;
  return (
    <p className={`text-sm transition-opacity ${loading ? "opacity-50" : ""}`} aria-live="polite">
      <span className="font-semibold tabular-nums text-zinc-900">{t("marketing.audienceCount", { count: audience.count })}</span>
      {audience.sample.length > 0 && (
        <span className="text-zinc-500">
          {" · "}
          {audience.sample.slice(0, 3).join(", ")}
          {audience.count > 3 ? "…" : ""}
        </span>
      )}
    </p>
  );
}

/** Create (segment = null) or edit a saved audience. */
export function AudienceSheet({ open, onClose, segment, onSaved }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [rules, setRules] = useState([]);
  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setName(segment?.name ?? "");
      setRules(segment?.rules ?? [{ ...CHOICES[0].rule }]);
    }
  }

  const save = useMutation({
    mutationFn: () => {
      const body = { name, rules: completeRules(rules) };
      return (segment ? apiClient.put(`/marketing/segments/${segment.id}`, body) : apiClient.post("/marketing/segments", body)).then((r) => r.data);
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["segments"] });
      toast.success(t(segment ? "marketing.audienceUpdated" : "marketing.audienceCreated"));
      onClose();
      onSaved?.(saved);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const remove = useMutation({
    mutationFn: () => apiClient.delete(`/marketing/segments/${segment.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segments"] });
      toast.success(t("marketing.audienceDeleted"));
      onClose();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t(segment ? "marketing.editAudience" : "marketing.newAudience")}
      footer={
        <>
          {segment && (
            <Button variant="danger" className="mr-auto" disabled={remove.isPending} onClick={() => remove.mutate()}>
              {t("common.delete")}
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <button type="submit" form="audience-form" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? t("common.saving") : t("common.save")}
          </button>
        </>
      }
    >
      <form
        id="audience-form"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label={t("marketing.audienceName")}>
          <input className="input" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("marketing.audienceNameHint")} />
        </Field>
        <div>
          <span className="label">{t("marketing.rule.heading")}</span>
          <RulesEditor rules={rules} onChange={setRules} />
        </div>
        <p className="text-xs text-zinc-500">{t("marketing.consentNote")}</p>
      </form>
    </Sheet>
  );
}
