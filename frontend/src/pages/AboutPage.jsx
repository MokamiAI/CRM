import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { APP_FULL_NAME, APP_NAME, BrandMark } from "../components/Brand";
import LanguagePicker from "../components/LanguagePicker";
import { IntervalToggle, PlanCard } from "../components/Billing";
import { ContactForm } from "./PublicPages";
import { usePlans } from "../hooks/useApi";
import { LANGUAGES } from "../i18n/languages";
import pkg from "../../package.json";

export const FEATURES = ["sales", "billing", "messages", "marketing", "languages", "companies"];
const ICONS = {
  sales: "M3 4h5v16H3zM10 4h5v11h-5zM17 4h4v7h-4z",
  billing: "M6 3h9l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1ZM14 3v5h5M9 13h6M9 17h4",
  messages: "M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 4V6Z",
  marketing: "M3 10.5v3a1 1 0 0 0 1 1h2l6 4.5V5L6 9.5H4a1 1 0 0 0-1 1ZM16 9a3.5 3.5 0 0 1 0 6",
  languages: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9s1.3-6.5 3.8-9Z",
  companies: "M12 3 4 7v6c0 4.4 3.4 7.6 8 8 4.6-.4 8-3.6 8-8V7l-8-4ZM9 12l2 2 4-4",
};
// Optional, set per deployment (VITE_SUPPORT_EMAIL in frontend/.env).
const SUPPORT_EMAIL = import.meta.env.VITE_SUPPORT_EMAIL;
const FOUNDER = "Mokami Johannes";

export function FeatureIcon({ name }) {
  return (
    <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5" aria-hidden="true">
        <path d={ICONS[name]} />
      </svg>
    </span>
  );
}

/** What YGT is: open to everyone, signed in or not. */
export default function AboutPage() {
  const { t } = useTranslation();
  const { user } = useAuth();

  return (
    <div className="min-h-[100dvh] bg-white">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[28rem] overflow-hidden" aria-hidden="true">
        <span className="aurora-blob -left-24 top-[-4rem] h-80 w-80 bg-violet-300" />
        <span className="aurora-blob right-[-6rem] top-[2rem] h-80 w-80 bg-sky-300" />
      </div>
      <div className="safe-top relative mx-auto max-w-4xl px-6">
        <header className="flex items-center gap-2.5 py-6">
          {/* Home for people signed in; the sign-in page for everyone else. */}
          <Link to="/" className="flex items-center gap-2.5 rounded-lg">
            <BrandMark size="sm" />
            <span className="text-[15px] font-semibold tracking-tight text-zinc-900">{APP_NAME}</span>
          </Link>
          <div className="ml-auto flex items-center gap-3">
            <LanguagePicker />
            <Link to={user ? "/" : "/login"} className="btn btn-secondary !h-9 !text-sm">
              {t(user ? "about.backToApp" : "login.signIn")}
            </Link>
          </div>
        </header>

        <section className="py-12 text-center sm:py-16">
          <BrandMark size="lg" className="mx-auto" join />
          <h1 className="mt-6 text-4xl font-semibold tracking-tight text-zinc-900 sm:text-5xl">{APP_FULL_NAME}</h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-zinc-600">{t("about.tagline")}</p>
          <p className="mx-auto mt-3 max-w-xl text-sm text-zinc-500">{t("about.meaning", { name: APP_NAME, full: APP_FULL_NAME })}</p>
        </section>

        <section className="mx-auto mb-14 max-w-2xl" aria-labelledby="about-story">
          <h2 id="about-story" className="text-xs font-semibold uppercase tracking-[0.12em] text-indigo-600">
            {t("about.story.title")}
          </h2>
          <div className="mt-4 space-y-4 text-[15px] leading-relaxed text-zinc-700">
            {["p1", "p2", "p3"].map((k) => (
              <p key={k}>{t(`about.story.${k}`, { full: APP_FULL_NAME, founder: FOUNDER })}</p>
            ))}
          </div>
          <figure className="mt-8 border-l-2 border-indigo-200 pl-5">
            <blockquote className="brand-text text-3xl font-semibold tracking-tight sm:text-4xl">{APP_FULL_NAME}.</blockquote>
            <figcaption className="mt-2 text-sm text-zinc-500">
              <span className="font-medium text-zinc-900">{FOUNDER}</span> · {t("about.story.role")}
            </figcaption>
          </figure>
        </section>

        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label={t("about.featuresTitle")}>
          {FEATURES.map((key, i) => (
            <div key={key} className="card stagger-rise p-5" style={{ "--i": i }}>
              <FeatureIcon name={key} />
              <h2 className="mt-3 font-semibold text-zinc-900">{t(`about.features.${key}.title`)}</h2>
              <p className="mt-1 text-sm leading-relaxed text-zinc-600">{t(`about.features.${key}.body`)}</p>
            </div>
          ))}
        </section>

        <Pricing />

        <section className="mt-14 grid gap-6 rounded-2xl p-6 ring-1 ring-inset ring-zinc-200 sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]" aria-labelledby="about-contact">
          <div>
            <h2 id="about-contact" className="text-2xl font-semibold tracking-tight text-zinc-900">
              {t("contact.title")}
            </h2>
            <p className="mt-2 text-sm text-zinc-600">{t("contact.intro")}</p>
          </div>
          <ContactForm compact />
        </section>

        <section className="mt-10 grid gap-6 rounded-2xl bg-zinc-50 p-6 ring-1 ring-inset ring-zinc-200/70 sm:grid-cols-2 sm:p-8">
          <div>
            <h2 className="font-semibold text-zinc-900">{t("about.privacyTitle")}</h2>
            <ul className="mt-3 space-y-2 text-sm text-zinc-600">
              {["separate", "encrypted", "optOut", "yours"].map((k) => (
                <li key={k} className="flex gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500" aria-hidden="true" />
                  {t(`about.privacy.${k}`)}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h2 className="font-semibold text-zinc-900">{t("about.languagesTitle")}</h2>
            <p className="mt-3 text-sm leading-relaxed text-zinc-600">{LANGUAGES.map((l) => l.name).join(" · ")}</p>
            <h2 className="mt-6 font-semibold text-zinc-900">{t("about.supportTitle")}</h2>
            <p className="mt-3 text-sm text-zinc-600">
              {SUPPORT_EMAIL ? (
                <a href={`mailto:${SUPPORT_EMAIL}`} className="font-medium text-indigo-600 hover:text-indigo-700">
                  {SUPPORT_EMAIL}
                </a>
              ) : (
                t("about.supportAdmin")
              )}
            </p>
          </div>
        </section>

        <footer className="safe-bottom flex flex-wrap items-center justify-between gap-2 py-10 text-xs text-zinc-400">
          <span>
            © {new Date().getFullYear()} {APP_NAME} · {t("about.madeIn")}
          </span>
          <span className="flex flex-wrap gap-x-4 gap-y-1">
            <Link to="/terms" className="hover:text-zinc-700">
              {t("legal.terms")}
            </Link>
            <Link to="/privacy" className="hover:text-zinc-700">
              {t("legal.privacy")}
            </Link>
            <Link to="/refunds" className="hover:text-zinc-700">
              {t("legal.refunds")}
            </Link>
            <span className="tabular-nums">{t("about.version", { version: pkg.version })}</span>
          </span>
        </footer>
      </div>
    </div>
  );
}

/** Larger organisations: the same YGT, priced per quote, with help to set up. */
function EnterpriseCard() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col rounded-2xl bg-zinc-50 p-5 ring-1 ring-inset ring-zinc-200">
      <h3 className="font-semibold text-zinc-900">{t("billing.planName.enterprise")}</h3>
      <p className="mt-0.5 text-sm text-zinc-500">{t("billing.tagline.enterprise")}</p>
      <p className="mt-4 text-3xl font-semibold tracking-tight text-zinc-900">{t("billing.enterprise.price")}</p>
      <p className="mt-0.5 text-sm text-zinc-500">{t("billing.enterprise.priceHint")}</p>
      <ul className="mt-4 flex-1 space-y-1.5 text-sm text-zinc-600">
        {["scale", "setup", "support"].map((key) => (
          <li key={key} className="flex gap-2">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={2} className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" aria-hidden="true">
              <path d="m3.5 8.5 3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {t(`billing.enterprise.lines.${key}`)}
          </li>
        ))}
      </ul>
      <Link to="/contact" className="btn btn-secondary mt-5 w-full">
        {t("billing.enterprise.cta")}
      </Link>
    </div>
  );
}

/** Plans and prices. Signed out: start a free trial. Admins: go to Billing. */
export function Pricing() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data: plans, isError, refetch, isFetching } = usePlans();
  const [interval, setInterval] = useState("monthly");
  const [seats, setSeats] = useState({});
  const cta = (plan) => {
    if (!user) {
      return (
        <Link to={`/register?plan=${plan.key}`} className={`btn ${plan.key === "grow" ? "btn-primary" : "btn-secondary"} w-full`}>
          {t("about.pricing.startTrial")}
        </Link>
      );
    }
    if (user.role === "admin") {
      return (
        <Link to="/settings?tab=billing" className={`btn ${plan.key === "grow" ? "btn-primary" : "btn-secondary"} w-full`}>
          {t("billing.choose", { plan: plan.name })}
        </Link>
      );
    }
    return null;
  };
  return (
    <section className="mt-14" aria-labelledby="about-pricing">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 id="about-pricing" className="text-2xl font-semibold tracking-tight text-zinc-900">
            {t("about.pricing.title")}
          </h2>
          <p className="mt-1 max-w-xl text-sm text-zinc-600">{t("about.pricing.intro", { days: 14 })}</p>
        </div>
        {plans && <IntervalToggle value={interval} onChange={setInterval} />}
      </div>
      {/* The section never vanishes: placeholders while the prices load,
          and a way to try again if they can't. */}
      {!plans && isError && !isFetching ? (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-zinc-50 px-5 py-4 ring-1 ring-inset ring-zinc-200/70">
          <p className="text-sm text-zinc-600">{t("common.loadError")}</p>
          <button type="button" onClick={() => refetch()} className="btn btn-secondary !h-9 !text-sm">
            {t("common.tryAgain")}
          </button>
        </div>
      ) : !plans ? (
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-72 animate-pulse rounded-2xl bg-zinc-100 motion-reduce:animate-none" />
          ))}
        </div>
      ) : (
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {plans.map((plan) => (
            <PlanCard
              key={plan.key}
              plan={plan}
              interval={interval}
              users={seats[plan.key] ?? plan.min_users}
              onUsers={(n) => setSeats((s) => ({ ...s, [plan.key]: n }))}
              highlight={plan.key === "grow"}
              badge={plan.key === "grow" ? t("billing.popular") : undefined}
              action={cta(plan)}
            />
          ))}
          <EnterpriseCard />
        </div>
      )}
      <p className="mt-3 text-xs text-zinc-500">{t("about.pricing.footnote")}</p>
    </section>
  );
}
