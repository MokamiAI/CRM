import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { APP_FULL_NAME, APP_NAME, BrandMark } from "../components/Brand";
import LanguagePicker from "../components/LanguagePicker";
import LoginShowcase from "../components/LoginShowcase";
import { FEATURES, FeatureIcon, Pricing } from "./AboutPage";
import { PublicFooter } from "./PublicPages";

const PAINS = ["scattered", "followUps", "chasing"];
const STEPS = ["setup", "sell", "grow"];
const POINTS = ["noCard", "trial", "cancel", "languages"];
const FAQS = ["card", "vat", "import", "phone", "data", "help"];

/** yougt.co.za for people who aren't signed in: what YGT is, and the way in. */
export default function HomePage() {
  const { t } = useTranslation();
  const start = (
    <Link to="/register" className="btn btn-primary !h-11 !px-5 !text-[15px]">
      {t("home.hero.cta")}
    </Link>
  );

  return (
    <div className="min-h-[100dvh] bg-white">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[36rem] overflow-hidden" aria-hidden="true">
        <span className="aurora-blob -left-24 top-[-4rem] h-96 w-96 bg-violet-300" />
        <span className="aurora-blob right-[-6rem] top-[4rem] h-96 w-96 bg-sky-300" />
      </div>

      <div className="safe-top relative mx-auto max-w-6xl px-5 sm:px-6">
        <header className="flex items-center gap-3 py-5">
          <Link to="/" className="flex items-center gap-2.5 rounded-lg">
            <BrandMark size="sm" />
            <span className="text-[15px] font-semibold tracking-tight text-zinc-900">{APP_NAME}</span>
          </Link>
          <nav className="ml-6 hidden items-center gap-5 text-sm text-zinc-600 md:flex" aria-label={t("home.nav.label")}>
            <a href="#features" className="hover:text-zinc-900">{t("home.nav.features")}</a>
            <a href="#pricing" className="hover:text-zinc-900">{t("home.nav.pricing")}</a>
            <a href="#faq" className="hover:text-zinc-900">{t("home.nav.faq")}</a>
            <Link to="/about" className="hover:text-zinc-900">{t("about.link")}</Link>
          </nav>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <LanguagePicker />
            <Link to="/login" className="btn btn-secondary !h-9 !text-sm">
              {t("login.signIn")}
            </Link>
            <Link to="/register" className="btn btn-primary hidden !h-9 !text-sm sm:inline-flex">
              {t("home.nav.start")}
            </Link>
          </div>
        </header>

        {/* What it is, for whom, and the way in. */}
        <section className="grid items-center gap-10 py-10 sm:py-14 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-indigo-600">{t("home.hero.eyebrow")}</p>
            <h1 className="mt-3 text-4xl font-semibold tracking-tight text-zinc-900 sm:text-5xl lg:text-[3.4rem] lg:leading-[1.05]">
              {t("home.hero.title")}
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-zinc-600">{t("home.hero.body", { name: APP_NAME })}</p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              {start}
              <a href="#pricing" className="btn btn-secondary !h-11 !px-5 !text-[15px]">
                {t("home.hero.secondary")}
              </a>
            </div>
            <ul className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-sm text-zinc-600">
              {POINTS.map((k) => (
                <li key={k} className="flex items-center gap-1.5">
                  <svg viewBox="0 0 16 16" className="h-4 w-4 text-emerald-600" fill="currentColor" aria-hidden="true">
                    <path d="M12.7 4.3a1 1 0 0 1 0 1.4l-5.5 5.5a1 1 0 0 1-1.4 0L3.3 8.7a1 1 0 1 1 1.4-1.4l1.8 1.8 4.8-4.8a1 1 0 0 1 1.4 0Z" />
                  </svg>
                  {t(`home.points.${k}`)}
                </li>
              ))}
            </ul>
          </div>
          <div className="h-[22rem] min-w-0 overflow-hidden rounded-3xl shadow-pop ring-1 ring-zinc-900/5 sm:h-[26rem]">
            <LoginShowcase />
          </div>
        </section>

        {/* The everyday problems it takes away. */}
        <section className="py-12" aria-labelledby="home-pain">
          <h2 id="home-pain" className="text-center text-3xl font-semibold tracking-tight text-zinc-900">{t("home.pain.title")}</h2>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {PAINS.map((k) => (
              <div key={k} className="card flex flex-col gap-3 p-5">
                <p className="text-[15px] text-zinc-500 line-through decoration-rose-300/80">{t(`home.pain.${k}.problem`)}</p>
                <p className="flex gap-2 text-[15px] font-medium text-zinc-900">
                  <span className="mt-0.5 text-indigo-600" aria-hidden="true">→</span>
                  {t(`home.pain.${k}.fix`, { name: APP_NAME })}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* How it works: a real sequence, so numbered. */}
        <section className="py-12" aria-labelledby="home-how">
          <h2 id="home-how" className="text-3xl font-semibold tracking-tight text-zinc-900">{t("home.how.title")}</h2>
          <p className="mt-2 max-w-2xl text-zinc-600">{t("home.how.intro")}</p>
          <ol className="mt-8 grid gap-4 md:grid-cols-3">
            {STEPS.map((k, i) => (
              <li key={k} className="flex flex-col gap-2 rounded-2xl bg-zinc-50 p-5 ring-1 ring-inset ring-zinc-200/70">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold text-white">{i + 1}</span>
                <h3 className="mt-1 font-semibold text-zinc-900">{t(`home.how.${k}.title`)}</h3>
                <p className="text-sm leading-relaxed text-zinc-600">{t(`home.how.${k}.body`)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="features" className="scroll-mt-6 py-12" aria-labelledby="home-features">
          <h2 id="home-features" className="text-3xl font-semibold tracking-tight text-zinc-900">{t("home.features.title")}</h2>
          <p className="mt-2 max-w-2xl text-zinc-600">{t("home.features.intro")}</p>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((key) => (
              <div key={key} className="card p-5">
                <FeatureIcon name={key} />
                <h3 className="mt-3 font-semibold text-zinc-900">{t(`about.features.${key}.title`)}</h3>
                <p className="mt-1 text-sm leading-relaxed text-zinc-600">{t(`about.features.${key}.body`)}</p>
              </div>
            ))}
          </div>
        </section>

        <div id="pricing" className="scroll-mt-6">
          <Pricing />
        </div>

        <Faq />

        {/* The close, in YGT's own words. */}
        <section className="my-16 overflow-hidden rounded-3xl bg-zinc-950 px-6 py-12 text-center sm:px-10">
          <p className="brand-text text-3xl font-semibold tracking-tight sm:text-4xl">{APP_FULL_NAME}.</p>
          <h2 className="mx-auto mt-3 max-w-xl text-xl font-semibold text-white">{t("home.final.title")}</h2>
          <p className="mx-auto mt-2 max-w-xl text-zinc-400">{t("home.final.body")}</p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <Link to="/register" className="btn !h-11 !px-5 !text-[15px] bg-white text-zinc-900 hover:bg-zinc-100">
              {t("home.hero.cta")}
            </Link>
            <Link to="/contact" className="btn !h-11 !px-5 !text-[15px] bg-white/10 text-white hover:bg-white/15">
              {t("home.final.talk")}
            </Link>
          </div>
        </section>

        <PublicFooter />
      </div>
    </div>
  );
}

function Faq() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(null);
  return (
    <section id="faq" className="scroll-mt-6 py-12" aria-labelledby="home-faq">
      <h2 id="home-faq" className="text-3xl font-semibold tracking-tight text-zinc-900">{t("home.faq.title")}</h2>
      <ul className="mt-6 divide-y divide-zinc-200 rounded-2xl ring-1 ring-inset ring-zinc-200">
        {FAQS.map((k) => {
          const expanded = open === k;
          return (
            <li key={k}>
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : k)}
                className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left font-medium text-zinc-900 hover:bg-zinc-50"
              >
                {t(`home.faq.${k}.q`)}
                <svg viewBox="0 0 16 16" fill="currentColor" className={`h-4 w-4 shrink-0 text-zinc-400 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} aria-hidden="true">
                  <path d="M4.2 6.2a.75.75 0 0 1 1.06 0L8 8.94l2.74-2.74a.75.75 0 1 1 1.06 1.06l-3.27 3.27a.75.75 0 0 1-1.06 0L4.2 7.26a.75.75 0 0 1 0-1.06Z" />
                </svg>
              </button>
              {expanded && <p className="px-5 pb-5 text-[15px] leading-relaxed text-zinc-600">{t(`home.faq.${k}.a`)}</p>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
