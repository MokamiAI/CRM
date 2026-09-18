import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "../services/apiClient";

const EMPTY_FORM = {
  company_name: "",
  address: "",
  tax_number: "",
  default_currency: "",
  default_timezone: "",
  logo_url: "",
  invoice_prefix: "",
  quote_prefix: "",
  payment_terms_days: "30",
  sender_name: "",
  sender_email: "",
  smtp_host: "",
  smtp_port: "",
  smtp_username: "",
  smtp_password: "",
  smtp_use_tls: true,
};

function Field({ label, hint, children }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      {children}
      {hint ? <Text style={styles.hint}>{hint}</Text> : null}
    </View>
  );
}

function Section({ title, description, children }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {description ? <Text style={styles.sectionDescription}>{description}</Text> : null}
      {children}
    </View>
  );
}

export default function SettingsScreen() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiClient.get("/settings").then((res) => res.data),
  });

  const [form, setForm] = useState(EMPTY_FORM);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!data) return;
    setForm({
      ...EMPTY_FORM,
      ...data,
      smtp_password: "",
      payment_terms_days: String(data.payment_terms_days ?? ""),
      smtp_port: data.smtp_port != null ? String(data.smtp_port) : "",
    });
  }, [data]);

  const mutation = useMutation({
    mutationFn: (payload) => apiClient.patch("/settings", payload).then((res) => res.data),
    onSuccess: (updated) => {
      queryClient.setQueryData(["settings"], updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleSave() {
    const payload = {
      ...form,
      payment_terms_days: Number(form.payment_terms_days) || 0,
      smtp_port: form.smtp_port === "" ? null : Number(form.smtp_port),
    };
    if (!payload.smtp_password) delete payload.smtp_password;
    mutation.mutate(payload);
  }

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator />
        <Text style={styles.hint}>Loading settings…</Text>
      </View>
    );
  }
  if (isError) {
    return (
      <View style={styles.centered}>
        <Text style={styles.error}>Failed to load settings.</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Section title="Company">
        <Field label="Company name">
          <TextInput
            style={styles.input}
            value={form.company_name}
            onChangeText={(v) => update("company_name", v)}
          />
        </Field>
        <Field label="Tax number">
          <TextInput
            style={styles.input}
            value={form.tax_number ?? ""}
            onChangeText={(v) => update("tax_number", v)}
          />
        </Field>
        <Field label="Address" hint="Shown on invoice/quote PDFs">
          <TextInput
            style={[styles.input, styles.multiline]}
            multiline
            value={form.address ?? ""}
            onChangeText={(v) => update("address", v)}
          />
        </Field>
        <Field label="Default currency">
          <TextInput
            style={styles.input}
            value={form.default_currency}
            onChangeText={(v) => update("default_currency", v)}
          />
        </Field>
        <Field label="Default timezone">
          <TextInput
            style={styles.input}
            value={form.default_timezone}
            onChangeText={(v) => update("default_timezone", v)}
          />
        </Field>
      </Section>

      <Section title="Quotes & invoices">
        <Field label="Quote number prefix">
          <TextInput
            style={styles.input}
            value={form.quote_prefix}
            onChangeText={(v) => update("quote_prefix", v)}
          />
        </Field>
        <Field label="Invoice number prefix">
          <TextInput
            style={styles.input}
            value={form.invoice_prefix}
            onChangeText={(v) => update("invoice_prefix", v)}
          />
        </Field>
        <Field
          label="Payment terms (days)"
          hint="Default due date = issue date + this many days"
        >
          <TextInput
            style={styles.input}
            keyboardType="number-pad"
            value={form.payment_terms_days}
            onChangeText={(v) => update("payment_terms_days", v)}
          />
        </Field>
      </Section>

      <Section
        title="Outgoing email"
        description="The email address and SMTP account used to send invoices, quotes, and payment reminders to customers. Leave the SMTP fields blank to use the server default account instead of your own."
      >
        <Field label="Sender name" hint='e.g. "Acme Billing"'>
          <TextInput
            style={styles.input}
            value={form.sender_name ?? ""}
            onChangeText={(v) => update("sender_name", v)}
          />
        </Field>
        <Field label="Sender email" hint="Where customer replies will land">
          <TextInput
            style={styles.input}
            autoCapitalize="none"
            keyboardType="email-address"
            value={form.sender_email ?? ""}
            onChangeText={(v) => update("sender_email", v)}
          />
        </Field>
        <Field label="SMTP host">
          <TextInput
            style={styles.input}
            placeholder="smtp.gmail.com"
            autoCapitalize="none"
            value={form.smtp_host ?? ""}
            onChangeText={(v) => update("smtp_host", v)}
          />
        </Field>
        <Field label="SMTP port">
          <TextInput
            style={styles.input}
            placeholder="587"
            keyboardType="number-pad"
            value={form.smtp_port}
            onChangeText={(v) => update("smtp_port", v)}
          />
        </Field>
        <Field label="SMTP username">
          <TextInput
            style={styles.input}
            autoCapitalize="none"
            value={form.smtp_username ?? ""}
            onChangeText={(v) => update("smtp_username", v)}
          />
        </Field>
        <Field
          label="SMTP password"
          hint={data?.smtp_password_set ? "A password is already saved — leave blank to keep it." : undefined}
        >
          <TextInput
            style={styles.input}
            secureTextEntry
            placeholder={data?.smtp_password_set ? "••••••••" : ""}
            value={form.smtp_password}
            onChangeText={(v) => update("smtp_password", v)}
          />
        </Field>
        <View style={styles.switchRow}>
          <Text style={styles.label}>Use TLS</Text>
          <Switch
            value={form.smtp_use_tls}
            onValueChange={(v) => update("smtp_use_tls", v)}
          />
        </View>
      </Section>

      <TouchableOpacity
        style={[styles.button, mutation.isPending && styles.buttonDisabled]}
        onPress={handleSave}
        disabled={mutation.isPending}
      >
        <Text style={styles.buttonText}>
          {mutation.isPending ? "Saving…" : "Save settings"}
        </Text>
      </TouchableOpacity>
      {saved ? <Text style={styles.success}>Saved.</Text> : null}
      {mutation.isError ? <Text style={styles.error}>Failed to save settings.</Text> : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#f9fafb",
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f9fafb",
    gap: 8,
  },
  section: {
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#e5e7eb",
    padding: 16,
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 17,
    fontWeight: "700",
    color: "#1f2937",
    marginBottom: 4,
  },
  sectionDescription: {
    fontSize: 13,
    color: "#6b7280",
    marginBottom: 12,
  },
  field: {
    marginBottom: 14,
  },
  label: {
    fontSize: 14,
    fontWeight: "500",
    color: "#374151",
    marginBottom: 4,
  },
  hint: {
    fontSize: 12,
    color: "#6b7280",
    marginTop: 4,
  },
  input: {
    borderWidth: 1,
    borderColor: "#d1d5db",
    borderRadius: 6,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
  },
  multiline: {
    minHeight: 60,
    textAlignVertical: "top",
  },
  switchRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  button: {
    backgroundColor: "#4f46e5",
    borderRadius: 6,
    paddingVertical: 12,
    alignItems: "center",
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: "#fff",
    fontSize: 15,
    fontWeight: "600",
  },
  error: {
    color: "#dc2626",
    fontSize: 14,
    marginTop: 12,
    textAlign: "center",
  },
  success: {
    color: "#16a34a",
    fontSize: 14,
    marginTop: 12,
    textAlign: "center",
  },
});
