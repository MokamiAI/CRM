import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useActivities, useContacts, useCustomer, useDeal, useDealQuotes, useTeamMap, useTimeline } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import { useCustomFieldRows } from "../components/CustomFields";
import DealFormSheet from "../components/DealFormSheet";
import Sheet from "../components/Sheet";
import { BackLink } from "../components/DocumentView";
import { ActivityRow, ComposerSheet, QuickActions, STAGES, STAGE_LABELS, Timeline, industryLabel, useToggleActivity } from "../components/crm";
import { Avatar, Button, ButtonLink, ErrorState, Field, ListSkeleton, PageHeader, PlusIcon, StatusBadge } from "../components/ui";
import { errorMessage, formatDate, formatMoney } from "../utils/format";
import { celebrate } from "../utils/motion";

/**
 * Pipedrive's stage bar: where the deal is, and a one-click way to move it.
 * Segments up to the current stage are filled; each is a button.
 */
function StageBar({ stage, disabled, onMove }) {
  const { t } = useTranslation();
  const current = STAGES.findIndex((s) => s.value === stage);
  return (
    <div className="flex gap-1" role="group" aria-label={t("deal.stageBar")}>
      {STAGES.map((s, i) => {
        const reached = current >= 0 && i <= current;
        return (
          <button
            key={s.value}
            type="button"
            disabled={disabled || s.value === stage}
            aria-current={s.value === stage ? "step" : undefined}
            onClick={() => onMove(s.value)}
            style={reached ? { "--slices": STAGES.length, "--slice": i } : undefined}
            className={`group flex-1 rounded-md px-2 py-2 text-left text-xs font-medium transition-colors duration-150 disabled:cursor-default sm:text-[13px] ${
              reached ? "spectrum-slice text-white shadow-xs" : "bg-zinc-100 text-zinc-500 enabled:hover:bg-zinc-200 enabled:hover:text-zinc-800"
            } ${i === 0 ? "rounded-l-lg" : ""} ${i === STAGES.length - 1 ? "rounded-r-lg" : ""}`}
          >
            <span className="block truncate">{s.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function Card({ title, action, children, padded = false }) {
  return (
    <section className="card overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-zinc-100 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-zinc-900">{title}</h2>
        {action}
      </div>
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}

export default function DealDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const canManage = ["admin", "manager"].includes(user?.role);
  const queryClient = useQueryClient();

  const { data: deal, isLoading, isError, refetch } = useDeal(id);
  const { data: customer } = useCustomer(deal?.customer_id ?? "");
  const { data: contacts = [] } = useContacts(deal?.customer_id);
  const { data: activities = [] } = useActivities({ deal_id: id });
  const { data: quotes = [] } = useDealQuotes(id);
  const { data: timeline = [], isLoading: timelineLoading } = useTimeline("deal", id);
  const team = useTeamMap();
  const toggle = useToggleActivity();
  const customRows = useCustomFieldRows("deal", deal?.custom_fields);

  const [sheet, setSheet] = useState(null); // edit | activity | note | lost | delete
  const [lostReason, setLostReason] = useState("");
  const [composeType, setComposeType] = useState("call");
  const close = () => setSheet(null);

  const refresh = () => {
    for (const key of [["deal", id], ["deals"], ["timeline"]]) queryClient.invalidateQueries({ queryKey: key });
  };
  const move = useMutation({
    mutationFn: (body) => apiClient.patch(`/deals/${id}`, body),
    onSuccess: (_r, body) => {
      refresh();
      close();
      if (body.stage === "won") toast.success(t("deals.wonToast"));
      else if (body.stage === "lost") toast(t("deals.lostToast"));
      else toast.success(t("deal.movedTo", { stage: STAGE_LABELS[body.stage] }));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: () => apiClient.delete(`/deals/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deals"] });
      toast.success(t("deal.deleted"));
      navigate("/deals", { replace: true });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (isLoading) return <ListSkeleton rows={4} />;
  if (isError) return <ErrorState onRetry={refetch} />;

  const closed = deal.stage === "won" || deal.stage === "lost";
  const contact = contacts.find((c) => c.id === deal.contact_id);
  const open = activities.filter((a) => !a.done);
  const owner = team.get(deal.owner_id);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={<BackLink to="/deals">{t("nav.deals")}</BackLink>}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {deal.title}
            {closed && <StatusBadge status={deal.stage} />}
          </span>
        }
        subtitle={
          <>
            {formatMoney(deal.value)} ·{" "}
            <Link to={`/customers/${deal.customer_id}`} className="font-medium text-zinc-700 hover:underline">
              {customer?.name ?? "…"}
            </Link>
          </>
        }
        actions={
          canWrite && (
            <>
              <Button variant="secondary" onClick={() => setSheet("edit")}>
                {t("common.edit")}
              </Button>
              {closed ? (
                <Button variant="secondary" onClick={() => move.mutate({ stage: "negotiation" })}>
                  {t("deal.reopen")}
                </Button>
              ) : (
                <>
                  <Button
                    variant="danger"
                    onClick={() => {
                      setLostReason("");
                      setSheet("lost");
                    }}
                  >
                    {t("stage.lost")}
                  </Button>
                  <button type="button" className="btn bg-emerald-600 text-white shadow-xs hover:bg-emerald-700" onClick={(event) => {
                      celebrate(event.currentTarget);
                      move.mutate({ stage: "won" });
                    }}>
                    {t("stage.won")}
                  </button>
                </>
              )}
            </>
          )
        }
      />

      <QuickActions
        email={contact?.email ?? customer?.email}
        phone={contact?.phone ?? customer?.phone}
        canWrite={canWrite}
        onCompose={({ mode, type }) => {
          if (type) setComposeType(type);
          setSheet(mode);
        }}
      />

      {closed ? (
        <div className={`card flex items-center gap-3 px-5 py-4 text-sm ${deal.stage === "won" ? "text-emerald-800" : "text-red-800"}`}>
          <StatusBadge status={deal.stage} />
          <span>
            {t(deal.stage === "won" ? "deal.wonOn" : "deal.lostOn", { date: formatDate(deal.closed_at) })}
            {deal.lost_reason && ` · ${deal.lost_reason}`}
          </span>
        </div>
      ) : (
        <StageBar stage={deal.stage} disabled={!canWrite || move.isPending} onMove={(stage) => move.mutate({ stage })} />
      )}

      <div className="grid items-start gap-6 lg:grid-cols-12">
        {/* Left: the facts */}
        <aside className="space-y-6 lg:col-span-3">
          <Card title={t("deal.details")} padded>
            <dl className="space-y-3 text-sm">
              {[
                [t("deals.col.value"), formatMoney(deal.value)],
                [t("deals.col.stage"), STAGE_LABELS[deal.stage]],
                [t("deals.col.expectedClose"), formatDate(deal.expected_close_date)],
                [t("deals.col.industry"), industryLabel(deal.industry) || "—"],
                [t("deals.col.owner"), owner?.full_name ?? t("dealForm.unassigned")],
                [t("deal.created"), formatDate(deal.created_at)],
                ...customRows,
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs text-zinc-500">{label}</dt>
                  <dd className="mt-0.5 font-medium text-zinc-900">{value}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <Card title={t("deal.person")}>
            {contact ? (
              <div className="flex items-start gap-3 p-5">
                <Avatar name={`${contact.first_name} ${contact.last_name ?? ""}`} />
                <div className="min-w-0 text-sm">
                  <p className="font-medium text-zinc-900">{[contact.first_name, contact.last_name].filter(Boolean).join(" ")}</p>
                  {contact.job_title && <p className="text-zinc-500">{contact.job_title}</p>}
                  {contact.email && (
                    <a href={`mailto:${contact.email}`} className="mt-1 block truncate text-zinc-700 hover:underline">
                      {contact.email}
                    </a>
                  )}
                  {contact.phone && (
                    <a href={`tel:${contact.phone}`} className="block text-zinc-700 hover:underline">
                      {contact.phone}
                    </a>
                  )}
                </div>
              </div>
            ) : (
              <p className="px-5 py-4 text-sm text-zinc-500">{t("deal.noPerson")}</p>
            )}
          </Card>
        </aside>

        {/* Middle: what's next, then what happened */}
        <div className="min-w-0 space-y-6 lg:col-span-6">
          <Card
            title={t("deal.nextSteps")}
            action={
              canWrite && (
                <div className="flex gap-1.5">
                  <Button variant="secondary" className="!h-8 !px-2.5 !text-xs" onClick={() => setSheet("note")}>
                    {t("composer.addNote")}
                  </Button>
                  <Button className="!h-8 !px-2.5 !text-xs" onClick={() => setSheet("activity")}>
                    <PlusIcon className="h-3.5 w-3.5" /> {t("composer.schedule")}
                  </Button>
                </div>
              )
            }
          >
            {open.length ? (
              <ul className="divide-y divide-zinc-100">
                {open.map((a) => (
                  <ActivityRow key={a.id} activity={a} onToggle={toggle.mutate} />
                ))}
              </ul>
            ) : (
              <div className="flex items-center gap-2 px-5 py-4 text-sm text-amber-700">
                <span className="h-2 w-2 rounded-full bg-amber-500" aria-hidden="true" />
                {t("deal.nothingScheduled")}
              </div>
            )}
          </Card>
          <Card title={t("deal.history")}>
            <Timeline items={timeline} hideDealLinks loading={timelineLoading} />
          </Card>
        </div>

        {/* Right: related records */}
        <aside className="space-y-6 lg:col-span-3">
          <Card
            title={t("nav.quotes")}
            action={
              canWrite &&
              !closed && (
                <Link to={`/quotes/new?customer=${deal.customer_id}&deal=${deal.id}`} className="text-xs font-medium text-zinc-500 hover:text-zinc-900">
                  {t("deal.newQuote")}
                </Link>
              )
            }
          >
            {quotes.length ? (
              <ul className="divide-y divide-zinc-100">
                {quotes.map((q) => (
                  <li key={q.id}>
                    <Link to={`/quotes/${q.id}`} className="flex items-center justify-between gap-2 px-5 py-3 text-sm hover:bg-zinc-50">
                      <span className="whitespace-nowrap font-medium text-zinc-900">{q.quote_number}</span>
                      <span className="flex items-center gap-2">
                        <span className="tabular-nums text-zinc-700">{formatMoney(q.total)}</span>
                        <StatusBadge status={q.status} />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-4 text-sm text-zinc-500">{t("deal.noQuotes")}</p>
            )}
          </Card>
          {canManage && (
            <Button variant="danger" className="w-full" onClick={() => setSheet("delete")}>
              {t("deal.delete")}
            </Button>
          )}
        </aside>
      </div>

      <DealFormSheet open={sheet === "edit"} onClose={close} deal={deal} />
      <ComposerSheet open={sheet === "activity"} onClose={close} mode="activity" dealId={id} initialType={composeType} />
      <ComposerSheet open={sheet === "note"} onClose={close} mode="note" dealId={id} />
      <Sheet
        open={sheet === "lost"}
        onClose={close}
        title={t("deals.markLostTitle")}
        footer={
          <>
            <Button variant="secondary" onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" disabled={move.isPending} onClick={() => move.mutate({ stage: "lost", lost_reason: lostReason || null })}>
              {t("deals.markLost")}
            </Button>
          </>
        }
      >
        <Field label={t("deals.lostReason")} hint={t("deals.lostReasonHint")}>
          <input className="input" value={lostReason} onChange={(e) => setLostReason(e.target.value)} placeholder={t("deals.lostReasonPlaceholder")} />
        </Field>
      </Sheet>
      <Sheet
        open={sheet === "delete"}
        onClose={close}
        title={t("deal.deleteTitle")}
        footer={
          <>
            <Button variant="secondary" onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
              {t("common.delete")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-zinc-600">
          {t("deal.deleteWarning")}
        </p>
      </Sheet>
    </div>
  );
}
