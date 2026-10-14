import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Avatar, StatusBadge } from "./ui";
import { RowEditButton } from "./crm";
import { useAuth } from "../context/AuthContext";
import { formatMoney, formatShortDate } from "../utils/format";

function balanceOf(invoice) {
  return Number(invoice.total) - Number(invoice.amount_paid);
}

// "R 500,00 due" under the total, only when part of it has been paid.
function PartPaid({ invoice }) {
  const { t } = useTranslation();
  const balance = balanceOf(invoice);
  if (!(Number(invoice.amount_paid) > 0 && balance > 0)) return null;
  return <p className="text-xs text-zinc-500">{t("invoices.amountDue", { amount: formatMoney(balance) })}</p>;
}

/** Invoices as a table from md up, stacked rows on phones. */
export default function InvoiceList({ invoices, customers }) {
  const { user } = useAuth();
  // A draft opens the editor; a sent, unpaid invoice opens its page, which
  // offers to correct it (managers and admins). Paid ones aren't edited.
  const editLink = (invoice) => {
    if (user?.role === "viewer") return null;
    if (invoice.status === "draft") return `/invoices/${invoice.id}/edit`;
    const manager = ["admin", "manager"].includes(user?.role);
    if (manager && ["sent", "overdue"].includes(invoice.status) && Number(invoice.amount_paid) === 0) return `/invoices/${invoice.id}?edit=1`;
    return null;
  };
  const { t } = useTranslation();
  const navigate = useNavigate();
  const nameOf = (invoice) => customers.get(invoice.customer_id)?.name ?? "…";

  return (
    <div className="card overflow-hidden">
      <table className="hidden w-full md:table">
        <thead className="table-head">
          <tr>
            <th>{t("invoices.col.invoice")}</th>
            <th>{t("invoices.col.customer")}</th>
            <th>{t("invoices.col.issued")}</th>
            <th>{t("invoices.col.due")}</th>
            <th>{t("invoices.col.status")}</th>
            <th className="text-right">{t("invoices.col.amount")}</th>
            <th className="w-12"><span className="sr-only">{t("common.edit")}</span></th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((invoice) => (
            <tr key={invoice.id} className="table-row" onClick={() => navigate(`/invoices/${invoice.id}`)}>
              <td className="whitespace-nowrap font-medium text-zinc-900">
                {/* A real link too, for keyboard users and open-in-new-tab. */}
                <Link to={`/invoices/${invoice.id}`} onClick={(e) => e.stopPropagation()} className="hover:underline">
                  {invoice.invoice_number}
                </Link>
              </td>
              <td>
                <div className="flex items-center gap-2.5">
                  <Avatar name={nameOf(invoice)} size="sm" />
                  <span className="truncate text-zinc-700">{nameOf(invoice)}</span>
                </div>
              </td>
              <td className="whitespace-nowrap text-zinc-500">{formatShortDate(invoice.issue_date)}</td>
              <td className={`whitespace-nowrap ${invoice.status === "overdue" ? "font-medium text-zinc-900" : "text-zinc-500"}`}>
                {formatShortDate(invoice.due_date)}
              </td>
              <td>
                <StatusBadge status={invoice.status} />
              </td>
              <td className="whitespace-nowrap text-right tabular-nums">
                <p className="font-medium text-zinc-900">{formatMoney(invoice.total)}</p>
                <PartPaid invoice={invoice} />
              </td>
              <td className="text-right">
                {editLink(invoice) && <RowEditButton label={t("edit.title", { number: invoice.invoice_number })} to={editLink(invoice)} />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <ul className="divide-y divide-zinc-100 md:hidden">
        {invoices.map((invoice) => (
          <li key={invoice.id}>
            <Link
              to={`/invoices/${invoice.id}`}
              className="flex items-center gap-3 px-4 py-3.5 transition-colors duration-150 active:bg-zinc-50"
            >
              <Avatar name={nameOf(invoice)} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate font-medium text-zinc-900">{nameOf(invoice)}</p>
                </div>
                <p className="truncate text-[13px] text-zinc-500">
                  {invoice.invoice_number} · {t("invoices.dueOn", { date: formatShortDate(invoice.due_date) })}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <p className="font-medium tabular-nums text-zinc-900">{formatMoney(invoice.total)}</p>
                <StatusBadge status={invoice.status} />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
