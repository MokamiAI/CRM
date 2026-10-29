import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { useAudience, useCampaigns, useSegments } from "../hooks/useApi";
import { AudienceSheet, useRuleText } from "../components/marketing";
import MarketingProspects from "../components/MarketingProspects";
import { PlanNotice } from "../components/Billing";
import { Button, EmptyState, ErrorState, FilterChips, ListSkeleton, PageHeader, PlusIcon, StatusBadge } from "../components/ui";
import { errorMessage, formatDateTime } from "../utils/format";

const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);

export function campaignDate(campaign, t) {
  if (campaign.status === "scheduled") return t("marketing.scheduledFor", { date: formatDateTime(campaign.scheduled_at, { dateStyle: "medium", timeStyle: "short" }) });
  if (campaign.sent_at) return t("marketing.sentOn", { date: formatDateTime(campaign.sent_at, { dateStyle: "medium", timeStyle: "short" }) });
  return t("marketing.editedOn", { date: formatDateTime(campaign.updated_at, { dateStyle: "medium" }) });
}

export default function MarketingPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const canWrite = user?.role !== "viewer";
  const [tab, setTab] = useState("campaigns");
  const [audienceSheet, setAudienceSheet] = useState(null); // null | "new" | segment
  const [addingProspect, setAddingProspect] = useState(false);

  const create = useMutation({
    mutationFn: () => apiClient.post("/marketing/campaigns", { name: t("marketing.untitled") }).then((r) => r.data),
    onSuccess: (campaign) => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      navigate(`/marketing/campaigns/${campaign.id}`);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <>
      <PageHeader
        title={t("nav.marketing")}
        subtitle={t("marketing.subtitle")}
        actions={
          canWrite &&
          (tab === "campaigns" ? (
            <Button onClick={() => create.mutate()} disabled={create.isPending}>
              <PlusIcon className="h-4 w-4" /> {t("marketing.newCampaign")}
            </Button>
          ) : tab === "prospects" ? (
            <Button onClick={() => setAddingProspect(true)}>
              <PlusIcon className="h-4 w-4" /> {t("prospects.add")}
            </Button>
          ) : (
            <Button onClick={() => setAudienceSheet("new")}>
              <PlusIcon className="h-4 w-4" /> {t("marketing.newAudience")}
            </Button>
          ))
        }
      />
      <PlanNotice feature="marketing" />
      <FilterChips
        value={tab}
        onChange={setTab}
        options={[
          { value: "campaigns", label: t("marketing.campaigns") },
          { value: "audiences", label: t("marketing.audiences") },
          { value: "prospects", label: t("prospects.tab") },
        ]}
      />
      {tab === "campaigns" ? (
        <Campaigns onCreate={canWrite ? () => create.mutate() : null} />
      ) : tab === "prospects" ? (
        <MarketingProspects adding={addingProspect} onAdded={(what) => setAddingProspect(what === "open")} />
      ) : (
        <Audiences onEdit={canWrite ? setAudienceSheet : null} />
      )}
      <AudienceSheet
        open={audienceSheet !== null}
        onClose={() => setAudienceSheet(null)}
        segment={audienceSheet === "new" ? null : audienceSheet}
      />
    </>
  );
}

function Kpi({ label, value, detail }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-zinc-900">{value}</p>
      {detail && <p className="mt-0.5 text-xs text-zinc-500">{detail}</p>}
    </div>
  );
}

function Campaigns({ onCreate }) {
  const { t } = useTranslation();
  const { data = [], isLoading, isError, refetch } = useCampaigns();
  const { data: everyone } = useAudience([]);

  if (isLoading) return <ListSkeleton />;
  if (isError) return <ErrorState onRetry={refetch} />;

  const sent = data.filter((c) => c.stats.sent > 0);
  const delivered = sent.reduce((n, c) => n + c.stats.sent, 0);
  const opened = sent.reduce((n, c) => n + c.stats.opened, 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Kpi label={t("marketing.kpi.subscribers")} value={everyone?.count ?? "—"} detail={t("marketing.kpi.subscribersDetail")} />
        <Kpi label={t("marketing.kpi.sent")} value={sent.length} detail={t("marketing.kpi.sentDetail", { count: delivered })} />
        <Kpi label={t("marketing.kpi.openRate")} value={`${pct(opened, delivered)}%`} detail={t("marketing.kpi.openRateDetail")} />
      </div>

      {data.length === 0 ? (
        <EmptyState
          title={t("marketing.noCampaigns")}
          description={t("marketing.noCampaignsHint")}
          action={onCreate && <Button onClick={onCreate}>{t("marketing.newCampaign")}</Button>}
        />
      ) : (
        <ul className="card divide-y divide-zinc-100 overflow-hidden">
          {data.map((c) => (
            <li key={c.id}>
              <Link
                to={`/marketing/campaigns/${c.id}`}
                className="flex flex-col gap-2 px-4 py-3.5 transition-colors duration-150 hover:bg-zinc-50 sm:flex-row sm:items-center sm:gap-4 sm:px-5"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate font-medium text-zinc-900">{c.name}</p>
                    <StatusBadge status={c.status} />
                  </div>
                  <p className="truncate text-[13px] text-zinc-500">
                    {c.subject || t("marketing.noSubject")} · {campaignDate(c, t)}
                  </p>
                </div>
                {c.stats.recipients > 0 && (
                  <dl className="flex shrink-0 gap-5 text-right text-[13px]">
                    <div>
                      <dt className="text-zinc-500">{t("marketing.stat.recipients")}</dt>
                      <dd className="font-medium tabular-nums text-zinc-900">{c.stats.recipients}</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">{t("marketing.stat.opened")}</dt>
                      <dd className="font-medium tabular-nums text-zinc-900">{pct(c.stats.opened, c.stats.sent)}%</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">{t("marketing.stat.unsubscribed")}</dt>
                      <dd className="font-medium tabular-nums text-zinc-900">{c.stats.unsubscribed}</dd>
                    </div>
                  </dl>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SegmentRow({ segment, onEdit }) {
  const { t } = useTranslation();
  const ruleText = useRuleText();
  const { data: audience } = useAudience(segment.rules);
  const Tag = onEdit ? "button" : "div";
  return (
    <li>
      <Tag
        {...(onEdit && { type: "button", onClick: () => onEdit(segment) })}
        className="flex w-full items-center gap-4 px-4 py-3.5 text-left transition-colors duration-150 hover:bg-zinc-50 sm:px-5"
      >
        <div className="min-w-0 flex-1">
          <p className="font-medium text-zinc-900">{segment.name}</p>
          <p className="truncate text-[13px] text-zinc-500">
            {segment.rules.length ? segment.rules.map(ruleText).join(" · ") : t("marketing.rule.everyone")}
          </p>
        </div>
        <span className="shrink-0 text-sm font-medium tabular-nums text-zinc-700">
          {audience ? t("marketing.audienceCount", { count: audience.count }) : "…"}
        </span>
      </Tag>
    </li>
  );
}

function Audiences({ onEdit }) {
  const { t } = useTranslation();
  const { data = [], isLoading, isError, refetch } = useSegments();
  if (isLoading) return <ListSkeleton />;
  if (isError) return <ErrorState onRetry={refetch} />;
  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-500">{t("marketing.audiencesIntro")}</p>
      {data.length === 0 ? (
        <EmptyState
          title={t("marketing.noAudiences")}
          description={t("marketing.noAudiencesHint")}
          action={onEdit && <Button onClick={() => onEdit("new")}>{t("marketing.newAudience")}</Button>}
        />
      ) : (
        <ul className="card divide-y divide-zinc-100 overflow-hidden">
          {data.map((s) => (
            <SegmentRow key={s.id} segment={s} onEdit={onEdit} />
          ))}
        </ul>
      )}
    </div>
  );
}
