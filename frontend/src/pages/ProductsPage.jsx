import { useDeferredValue, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useProducts } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import Sheet from "../components/Sheet";
import {
  Button,
  EmptyState,
  ErrorState,
  Field,
  FilterChips,
  ListSkeleton,
  PageHeader,
  SearchInput,
  PlusIcon,
  StatusBadge,
} from "../components/ui";
import { errorMessage, formatMoney } from "../utils/format";
import { onSpecial } from "../utils/products";

const EMPTY = { name: "", sku: "", description: "", unit_price: "", tax_rate: "15", image_url: "", special_price: "", special_until: "" };

const ACTIVE_FILTERS = [
  { value: "true", key: "status.active" },
  { value: "false", key: "status.inactive" },
  { value: "all", key: "common.all" },
];

export default function ProductsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const canDeactivate = ["admin", "manager"].includes(user?.role);

  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("true");
  const deferredSearch = useDeferredValue(search.trim());
  const { data, isLoading, isError, refetch } = useProducts({
    ...(deferredSearch && { search: deferredSearch }),
    ...(activeFilter !== "all" && { is_active: activeFilter }),
  });

  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const queryClient = useQueryClient();

  function openEditor(product) {
    setEditing(product ?? "new");
    setForm(
      product
        ? {
            name: product.name,
            sku: product.sku ?? "",
            description: product.description ?? "",
            unit_price: String(Number(product.unit_price)),
            tax_rate: String(Number(product.tax_rate)),
            image_url: product.image_url ?? "",
            special_price: product.special_price == null ? "" : String(Number(product.special_price)),
            special_until: product.special_until ?? "",
          }
        : EMPTY
    );
  }

  const save = useMutation({
    mutationFn: (payload) =>
      editing === "new"
        ? apiClient.post("/products", payload)
        : apiClient.patch(`/products/${editing.id}`, payload),
    onSuccess: () => {
      toast.success(t(editing === "new" ? "products.added" : "products.updated"));
      queryClient.invalidateQueries({ queryKey: ["products"] });
      setEditing(null);
    },
    onError: (error) => toast.error(errorMessage(error, t("products.saveFailed"))),
  });

  const deactivate = useMutation({
    mutationFn: (id) => apiClient.post(`/products/${id}/deactivate`),
    onSuccess: () => {
      toast.success(t("products.deactivated"));
      queryClient.invalidateQueries({ queryKey: ["products"] });
      setEditing(null);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  function handleSubmit(event) {
    event.preventDefault();
    save.mutate({
      name: form.name,
      sku: form.sku || null,
      description: form.description || null,
      unit_price: form.unit_price || "0",
      tax_rate: form.tax_rate || "0",
      image_url: form.image_url || null,
      special_price: form.special_price || null,
      special_until: form.special_price ? form.special_until || null : null,
    });
  }

  const update = (field) => (event) => setForm((prev) => ({ ...prev, [field]: event.target.value }));

  return (
    <>
      <PageHeader
        title={t("products.title")}
        subtitle={t("products.subtitle")}
        actions={
          canWrite && (
            <Button onClick={() => openEditor(null)}>
              <PlusIcon className="h-4 w-4" /> {t("products.new")}
            </Button>
          )
        }
      />
      <div className="md:flex md:items-start md:gap-3">
        <div className="md:flex-1">
          <SearchInput value={search} onChange={setSearch} placeholder={t("products.search")} />
        </div>
        <FilterChips options={ACTIVE_FILTERS.map((o) => ({ ...o, label: t(o.key) }))} value={activeFilter} onChange={setActiveFilter} />
      </div>

      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : data.length === 0 ? (
        <EmptyState
          title={t(deferredSearch ? "products.noMatch" : "products.none")}
          description={t(deferredSearch ? "products.noMatchHint" : "products.noneHint")}
          action={!deferredSearch && canWrite && <Button onClick={() => openEditor(null)}>{t("products.new")}</Button>}
        />
      ) : (
        <div className="card overflow-hidden">
          <table className="hidden w-full md:table">
            <thead className="table-head">
              <tr>
                <th>{t("products.col.name")}</th>
                <th>{t("products.col.sku")}</th>
                <th className="text-right">{t("document.tax")}</th>
                <th className="text-right">{t("editor.unitPrice")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((product) => (
                <tr key={product.id} className="table-row" onClick={() => canWrite && openEditor(product)}>
                  <td>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-zinc-900">{product.name}</span>
                      {!product.is_active && <StatusBadge status="inactive" />}
                      {onSpecial(product) && <SpecialBadge />}
                    </div>
                    {product.description && (
                      <p className="mt-0.5 max-w-md truncate text-[13px] text-zinc-500">{product.description}</p>
                    )}
                  </td>
                  <td className="font-mono text-[13px] text-zinc-500">{product.sku || "—"}</td>
                  <td className="text-right tabular-nums text-zinc-600">{Number(product.tax_rate)}%</td>
                  <td className="whitespace-nowrap text-right font-medium tabular-nums text-zinc-900">
                    <Price product={product} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="divide-y divide-zinc-100 md:hidden">
            {data.map((product) => (
              <li key={product.id}>
                <button
                  type="button"
                  onClick={() => canWrite && openEditor(product)}
                  className="flex w-full items-center justify-between gap-4 px-4 py-3.5 text-left transition-colors duration-150 active:bg-zinc-50"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-zinc-900">{product.name}</p>
                    <p className="truncate text-[13px] text-zinc-500">
                      {[product.sku, t("document.taxRate", { rate: Number(product.tax_rate) })].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {!product.is_active && <StatusBadge status="inactive" />}
                    {onSpecial(product) && <SpecialBadge />}
                    <span className="font-medium tabular-nums text-zinc-900">
                      <Price product={product} />
                    </span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Sheet
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={t(editing === "new" ? "products.new" : "products.edit")}
        footer={
          <>
            {editing !== "new" && editing?.is_active && canDeactivate && (
              <Button
                variant="danger"
                className="mr-auto"
                disabled={deactivate.isPending}
                onClick={() => deactivate.mutate(editing.id)}
              >
                {t("customerForm.deactivate")}
              </Button>
            )}
            <Button variant="secondary" onClick={() => setEditing(null)}>
              {t("common.cancel")}
            </Button>
            <button type="submit" form="product-form" className="btn btn-primary" disabled={save.isPending}>
              {save.isPending ? t("common.saving") : t("common.save")}
            </button>
          </>
        }
      >
        <form id="product-form" onSubmit={handleSubmit} className="space-y-4">
          <Field label={t("products.col.name")}>
            <input className="input" required value={form.name} onChange={update("name")} />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label={t("products.unitPriceExcl")}>
              <input
                className="input tabular-nums"
                inputMode="decimal"
                required
                pattern="\d+(\.\d{1,2})?"
                value={form.unit_price}
                onChange={update("unit_price")}
              />
            </Field>
            <Field label={t("products.taxRate")}>
              <input
                className="input tabular-nums"
                inputMode="decimal"
                pattern="\d+(\.\d{1,2})?"
                value={form.tax_rate}
                onChange={update("tax_rate")}
              />
            </Field>
          </div>
          <Field label={t("products.col.sku")}>
            <input className="input" autoCapitalize="characters" value={form.sku} onChange={update("sku")} />
          </Field>
          <Field label={t("editor.description")}>
            <textarea className="input" rows={2} value={form.description} onChange={update("description")} />
          </Field>
          <div className="space-y-4 border-t border-zinc-100 pt-4">
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{t("products.marketingHeading")}</p>
            <div className="grid grid-cols-2 gap-4">
              <Field label={t("products.specialPrice")} hint={t("products.specialPriceHint")}>
                <input
                  className="input tabular-nums"
                  inputMode="decimal"
                  pattern="\d+(\.\d{1,2})?"
                  value={form.special_price}
                  onChange={update("special_price")}
                />
              </Field>
              <Field label={t("products.specialUntil")}>
                <input className="input" type="date" value={form.special_until} disabled={!form.special_price} onChange={update("special_until")} />
              </Field>
            </div>
            <Field label={t("products.imageUrl")} hint={t("products.imageUrlHint")}>
              <input className="input" type="url" inputMode="url" autoCapitalize="none" value={form.image_url} onChange={update("image_url")} placeholder="https://" />
            </Field>
          </div>
        </form>
      </Sheet>
    </>
  );
}

function SpecialBadge() {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center rounded-full bg-rose-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-rose-700 ring-1 ring-rose-200/70">
      {t("products.special")}
    </span>
  );
}

function Price({ product }) {
  if (!onSpecial(product)) return formatMoney(product.unit_price);
  return (
    <>
      <span className="mr-1.5 text-[13px] font-normal text-zinc-400 line-through">{formatMoney(product.unit_price)}</span>
      <span className="text-rose-700">{formatMoney(product.special_price)}</span>
    </>
  );
}
