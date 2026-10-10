import { useDeferredValue, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useCustomerOverview } from "../hooks/useApi";
import i18n from "../i18n";
import { useAuth } from "../context/AuthContext";
import CustomerFormSheet from "../components/CustomerFormSheet";
import {
  Avatar,
  Button,
  EmptyState,
  ErrorState,
  FilterChips,
  ListSkeleton,
  PageHeader,
  PlusIcon,
  SearchInput,
  StatusBadge,
} from "../components/ui";
import { formatDate, formatMoney, formatMoneyCompact } from "../utils/format";

const ACTIVE_FILTERS = [
  { value: "true", key: "status.active" },
  { value: "false", key: "status.inactive" },
  { value: "all", key: "common.all" },
];

// "Today", "Yesterday", "5 days ago", then a date: how long since we
// last touched this customer, which is what a CRM list is scanned for.
function relativeDay(iso) {
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(iso).setHours(0, 0, 0, 0)) / 86_400_000);
  if (days <= 0) return i18n.t("due.today");
  if (days === 1) return i18n.t("time.yesterday");
  if (days < 30) return i18n.t("time.daysAgo", { count: days });
  return formatDate(iso);
}

export default function CustomersPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const navigate = useNavigate();

  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("true");
  const deferredSearch = useDeferredValue(search.trim());
  const { data, isLoading, isError, refetch } = useCustomerOverview({
    ...(deferredSearch && { search: deferredSearch }),
    ...(activeFilter !== "all" && { is_active: activeFilter }),
  });
  const [creating, setCreating] = useState(false);

  return (
    <>
      <PageHeader
        title={t("nav.customers")}
        subtitle={t("customers.subtitle")}
        actions={
          canWrite && (
            <Button onClick={() => setCreating(true)}>
              <PlusIcon className="h-4 w-4" /> {t("customerForm.newTitle")}
            </Button>
          )
        }
      />
      <div className="md:flex md:items-start md:gap-3">
        <div className="md:flex-1">
          <SearchInput value={search} onChange={setSearch} placeholder={t("customers.search")} />
        </div>
        <FilterChips options={ACTIVE_FILTERS.map((o) => ({ ...o, label: t(o.key) }))} value={activeFilter} onChange={setActiveFilter} />
      </div>

      {isLoading ? (
        <ListSkeleton />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : data.length === 0 ? (
        <EmptyState
          title={t(deferredSearch ? "customers.noMatch" : "customers.none")}
          description={t(deferredSearch ? "customers.noMatchHint" : "customers.noneHint")}
          action={!deferredSearch && canWrite && <Button onClick={() => setCreating(true)}>{t("customerForm.newTitle")}</Button>}
        />
      ) : (
        <div className="card overflow-hidden">
          <table className="hidden w-full md:table">
            <thead className="table-head">
              <tr>
                <th>{t("customers.col.customer")}</th>
                <th>{t("customers.col.openDeals")}</th>
                <th className="text-right">{t("customers.col.balance")}</th>
                <th>{t("customers.col.lastActivity")}</th>
                <th className="text-right">{t("invoices.col.status")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id} className="table-row" onClick={() => navigate(`/customers/${c.id}`)}>
                  <td>
                    <div className="flex items-center gap-3">
                      <Avatar name={c.name} size="sm" />
                      <div className="min-w-0">
                        <Link
                          to={`/customers/${c.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="font-medium text-zinc-900 hover:underline"
                        >
                          {c.name}
                        </Link>
                        <p className="truncate text-xs text-zinc-500">
                          {c.primary_contact ?? c.email ?? t("customers.noContact")}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="whitespace-nowrap text-zinc-600">
                    {c.open_deals ? (
                      <>
                        <span className="font-medium text-zinc-900">{c.open_deals}</span>
                        <span className="text-zinc-400"> · {formatMoneyCompact(c.pipeline_value)}</span>
                      </>
                    ) : (
                      <span className="text-zinc-400">—</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap text-right tabular-nums">
                    {Number(c.balance) > 0 ? (
                      <span className="inline-flex items-center gap-2">
                        {c.overdue_invoices > 0 && <StatusBadge status="overdue" />}
                        <span className="font-medium text-zinc-900">{formatMoney(c.balance)}</span>
                      </span>
                    ) : (
                      <span className="text-zinc-400">—</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap text-zinc-500">{c.last_activity_at ? relativeDay(c.last_activity_at) : "—"}</td>
                  <td className="text-right">
                    <StatusBadge status={c.is_active ? "active" : "inactive"} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="divide-y divide-zinc-100 md:hidden">
            {data.map((c) => (
              <li key={c.id}>
                <Link
                  to={`/customers/${c.id}`}
                  className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors duration-150 active:bg-zinc-50"
                >
                  <Avatar name={c.name} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-zinc-900">{c.name}</p>
                    <p className="truncate text-[13px] text-zinc-500">
                      {c.primary_contact ?? c.email ?? t("customers.noContact")}
                      {c.open_deals > 0 && ` · ${t("dashboard.openDeals", { count: c.open_deals })}`}
                    </p>
                  </div>
                  {Number(c.balance) > 0 ? (
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <span className="text-sm font-medium tabular-nums text-zinc-900">{formatMoney(c.balance)}</span>
                      {c.overdue_invoices > 0 && <StatusBadge status="overdue" />}
                    </div>
                  ) : (
                    !c.is_active && <StatusBadge status="inactive" />
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      <CustomerFormSheet
        open={creating}
        onClose={() => setCreating(false)}
        customer={null}
        onSaved={(customer) => navigate(`/customers/${customer.id}`)}
      />
    </>
  );
}
