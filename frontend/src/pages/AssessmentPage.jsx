import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { usePlans } from "../hooks/useApi";
import { APP_NAME } from "../components/Brand";
import { Field } from "../components/ui";
import { errorMessage } from "../utils/format";
import { PublicShell } from "./PublicPages";
import { FormError } from "./LoginPage";
import { PEOPLE } from "../components/home/HomePeople";
import { AREA_MAX, AREAS, ASSUMPTIONS, QUESTIONS, assess, band, planCost, toolsUsed } from "../components/assessment/model";

/*
 * The free business check-up: ten quick questions, a short "working it
 * out" moment, then a report with a score, the biggest gaps, the hours
 * YGT could give back and what that's worth against the plan's price.
 * Progress is kept for the tab (sessionStorage), so a refresh doesn't
 * lose it.
 */

const STORE = "ygt.checkup";
const rand = (n) => `R ${Math.round(n).toLocaleString("en-ZA").replace(/,/g, " ")}`;
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function load() {
  try {
    return JSON.parse(sessionStorage.getItem(STORE)) || null;
  } catch {
    return null;
  }
}
function save(state) {
  try {
    sessionStorage.setItem(STORE, JSON.stringify(state));
  } catch {
    /* private mode: progress just isn't kept */
  }
}

export default function AssessmentPage() {
  const saved = useMemo(load, []);
  const [stage, setStage] = useState(saved?.stage === "report" ? "report" : saved?.stage === "quiz" ? "quiz" : "intro");
  const [step, setStep] = useState(saved?.step ?? 0);
  const [answers, setAnswers] = useState(saved?.answers ?? {});

  useEffect(() => {
    save({ stage: stage === "analysing" ? "report" : stage, step, answers });
  }, [stage, step, answers]);
  // Block body: Chrome's scrollTo now returns a promise, which React would take for a cleanup.
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [stage]);

  function restart() {
    setAnswers({});
    setStep(0);
    setStage("quiz");
  }

  return (
    <PublicShell>
      <main className="pb-6 pt-2 sm:pt-6">
        {stage === "intro" && <Intro onStart={() => setStage("quiz")} />}
        {stage === "quiz" && (
          <Quiz
            step={step}
            answers={answers}
            onAnswer={(key, value) => setAnswers((prev) => ({ ...prev, [key]: value }))}
            onStep={setStep}
            onDone={() => setStage("analysing")}
          />
        )}
        {stage === "analysing" && <Analysing answers={answers} onDone={() => setStage("report")} />}
        {stage === "report" && <Report answers={answers} onRestart={restart} />}
      </main>
    </PublicShell>
  );
}

// ---------------------------------------------------------------- intro

function Intro({ onStart }) {
  const { t } = useTranslation();
  return (
    <section className="checkup-in relative isolate overflow-hidden rounded-3xl bg-zinc-950 px-6 py-12 text-center sm:px-12 sm:py-16">
      <span
        className="cta-glow pointer-events-none absolute left-1/2 top-1/2 -z-10 h-[40rem] w-[40rem] rounded-full opacity-25 blur-3xl"
        style={{ transform: "translate(-50%, -50%)", background: "conic-gradient(from 0deg, #6366f1, #a855f7, #38bdf8, #6366f1)" }}
        aria-hidden="true"
      />
      <p className="text-sm font-semibold text-indigo-300">{t("assessment.intro.eyebrow")}</p>
      <h1 className="mx-auto mt-3 max-w-2xl text-3xl font-semibold tracking-tight text-white sm:text-5xl">{t("assessment.intro.title")}</h1>
      <p className="mx-auto mt-4 max-w-xl text-zinc-300 sm:text-lg">{t("assessment.intro.lead", { name: APP_NAME })}</p>
      <ul className="mx-auto mt-8 grid max-w-2xl gap-3 text-left sm:grid-cols-3">
        {["score", "gaps", "time"].map((k, i) => (
          <li key={k} className="rounded-2xl bg-white/5 p-4 ring-1 ring-inset ring-white/10">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-500/20 text-sm font-semibold text-indigo-200">{i + 1}</span>
            <p className="mt-2 text-sm font-medium text-white">{t(`assessment.intro.get.${k}`)}</p>
          </li>
        ))}
      </ul>
      <button type="button" onClick={onStart} className="btn mt-9 !h-12 !px-7 !text-base bg-white text-zinc-900 hover:bg-zinc-100">
        {t("assessment.intro.start")}
      </button>
      <p className="mt-4 text-sm text-zinc-400">{t("assessment.intro.meta", { count: QUESTIONS.length })}</p>
    </section>
  );
}

// ---------------------------------------------------------------- quiz

function Quiz({ step, answers, onAnswer, onStep, onDone }) {
  const { t } = useTranslation();
  const q = QUESTIONS[step];
  const value = answers[q.key];
  const detected = toolsUsed(answers);
  const last = step === QUESTIONS.length - 1;
  const advance = useRef(null);
  useEffect(() => () => clearTimeout(advance.current), []);

  // The tool count starts from what the earlier answers already named.
  useEffect(() => {
    if (q.kind === "count" && value == null) onAnswer(q.key, Math.max(1, detected.length));
    if (q.kind === "range" && value == null) onAnswer(q.key, q.initial);
  }, [q, value, detected.length, onAnswer]);

  const next = () => (last ? onDone() : onStep(step + 1));
  const ready = q.kind === "multi" ? value?.length > 0 : value != null;

  function pick(option) {
    if (q.kind === "multi") {
      const list = value ?? [];
      onAnswer(q.key, list.includes(option) ? list.filter((v) => v !== option) : [...list, option]);
      return;
    }
    onAnswer(q.key, option);
    // One answer moves on by itself, after a beat to see it land.
    clearTimeout(advance.current);
    advance.current = setTimeout(next, reducedMotion() ? 0 : 280);
  }

  return (
    <section aria-labelledby="checkup-q" className="mx-auto max-w-3xl">
      <div className="flex items-center gap-3 text-sm text-zinc-500">
        <span className="font-medium tabular-nums text-zinc-700">{t("assessment.progress", { n: step + 1, total: QUESTIONS.length })}</span>
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-100" aria-hidden="true">
          <div className="checkup-bar h-full rounded-full bg-gradient-to-r from-indigo-600 to-violet-500" style={{ width: `${((step + 1) / QUESTIONS.length) * 100}%` }} />
        </div>
      </div>

      {/* Every tool named so far, collected as the person goes. */}
      <div className="mt-4 flex min-h-8 flex-wrap items-center gap-1.5" aria-live="polite">
        <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-zinc-400">{t("assessment.spotted", { count: detected.length })}</span>
        {detected.map((tool) => (
          <span key={tool} className="checkup-chip rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-900 ring-1 ring-inset ring-amber-600/20">
            {t(`assessment.tools.${tool}`)}
          </span>
        ))}
      </div>

      <div key={q.key} className="checkup-in mt-4 rounded-3xl bg-white p-5 shadow-pop ring-1 ring-zinc-900/5 sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">{t(`assessment.q.${q.key}.topic`)}</p>
        <h1 id="checkup-q" className="mt-1.5 text-2xl font-semibold tracking-tight text-zinc-900 sm:text-3xl">
          {t(`assessment.q.${q.key}.title`)}
        </h1>
        <p className="mt-1.5 text-zinc-600">{t(q.kind === "multi" ? "assessment.pickAll" : `assessment.q.${q.key}.hint`, { defaultValue: "" })}</p>

        <div className="mt-6">
          {q.kind === "single" || q.kind === "multi" ? (
            <Options q={q} value={value} onPick={pick} />
          ) : q.kind === "range" ? (
            <Volume q={q} value={value ?? q.initial} onChange={(v) => onAnswer(q.key, v)} />
          ) : (
            <ToolCount q={q} value={value ?? 1} detected={detected} onChange={(v) => onAnswer(q.key, v)} />
          )}
        </div>

        <div className="mt-8 flex items-center justify-between gap-3">
          <button type="button" className="btn btn-secondary" onClick={() => onStep(step - 1)} disabled={step === 0}>
            {t("assessment.back")}
          </button>
          {(q.kind !== "single" || value != null) && (
            <button type="button" className="btn btn-primary" onClick={next} disabled={!ready}>
              {last ? t("assessment.finish") : t("assessment.next")}
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

function Options({ q, value, onPick }) {
  const { t } = useTranslation();
  const multi = q.kind === "multi";
  const photo = (key) => PEOPLE.find((p) => p.key === key)?.photo;
  const label = (option) => (q.key === "industry" && option !== "other" ? t(`home.people.${option}.label`) : t(`assessment.q.${q.key}.options.${option}`));
  return (
    <div className={`grid gap-2.5 ${q.key === "industry" ? "grid-cols-2 sm:grid-cols-4" : "sm:grid-cols-2"}`}>
      {q.options.map((option) => {
        const on = multi ? value?.includes(option) : value === option;
        const src = q.key === "industry" ? photo(option) : null;
        return (
          <button
            key={option}
            type="button"
            aria-pressed={on}
            onClick={() => onPick(option)}
            className={`checkup-option group relative flex min-h-14 items-center gap-3 overflow-hidden rounded-2xl p-3.5 text-left text-[15px] font-medium ring-1 ring-inset ${
              on ? "bg-indigo-50 text-indigo-950 ring-2 ring-indigo-600" : "bg-white text-zinc-800 ring-zinc-200 hover:bg-zinc-50 hover:ring-zinc-300"
            } ${q.key === "industry" ? "flex-col items-stretch !p-2 text-sm" : ""}`}
          >
            {q.key === "industry" &&
              (src ? (
                <img src={src} alt="" className="aspect-[4/3] w-full rounded-xl object-cover" loading="lazy" />
              ) : (
                <span className="flex aspect-[4/3] w-full items-center justify-center rounded-xl bg-zinc-100 text-2xl text-zinc-400" aria-hidden="true">
                  ···
                </span>
              ))}
            {q.key !== "industry" && (
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center ${multi ? "rounded-md" : "rounded-full"} ring-1 ring-inset ${
                  on ? "bg-indigo-600 ring-indigo-600" : "bg-white ring-zinc-300"
                }`}
                aria-hidden="true"
              >
                {on && (
                  <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 text-white" fill="currentColor">
                    <path d="M12.7 4.3a1 1 0 0 1 0 1.4l-5.5 5.5a1 1 0 0 1-1.4 0L3.3 8.7a1 1 0 1 1 1.4-1.4l1.8 1.8 4.8-4.8a1 1 0 0 1 1.4 0Z" />
                  </svg>
                )}
              </span>
            )}
            <span className={q.key === "industry" ? "px-1 pb-0.5" : ""}>{label(option)}</span>
          </button>
        );
      })}
    </div>
  );
}

function Volume({ q, value, onChange }) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div className="rounded-2xl bg-zinc-50 p-5 ring-1 ring-inset ring-zinc-200/70">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-sm font-medium text-zinc-700">
          {t("assessment.q.volume.label")}
        </label>
        <span className="text-3xl font-semibold tabular-nums text-zinc-900">{value}</span>
      </div>
      <input
        id={id}
        type="range"
        min={q.min}
        max={q.max}
        step={q.step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="savings-range mt-3 w-full"
        style={{ "--fill": `${((value - q.min) / (q.max - q.min)) * 100}%` }}
      />
      <div className="mt-1 flex justify-between text-xs text-zinc-400">
        <span>{q.min}</span>
        <span>{q.max}+</span>
      </div>
    </div>
  );
}

function ToolCount({ q, value, detected, onChange }) {
  const { t } = useTranslation();
  const extra = value - detected.length;
  return (
    <div>
      <div className="rounded-2xl bg-amber-50/70 p-4 ring-1 ring-inset ring-amber-600/15">
        <p className="text-sm text-amber-950">{t("assessment.q.tools.counted", { count: detected.length })}</p>
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {detected.map((tool) => (
            <span key={tool} className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-amber-900 ring-1 ring-inset ring-amber-600/20">
              {t(`assessment.tools.${tool}`)}
            </span>
          ))}
        </div>
      </div>
      <div className="mt-6 flex items-center justify-center gap-5">
        <button type="button" className="btn btn-secondary !h-12 !w-12 !p-0 text-xl" onClick={() => onChange(Math.max(q.min, value - 1))} disabled={value <= q.min} aria-label={t("assessment.q.tools.less")}>
          −
        </button>
        <div className="min-w-24 text-center">
          <p className="text-5xl font-semibold tabular-nums tracking-tight text-zinc-900" aria-live="polite">
            {value}
            {value >= q.max ? "+" : ""}
          </p>
          <p className="text-sm text-zinc-500">{t("assessment.q.tools.unit", { count: value })}</p>
        </div>
        <button type="button" className="btn btn-secondary !h-12 !w-12 !p-0 text-xl" onClick={() => onChange(Math.min(q.max, value + 1))} disabled={value >= q.max} aria-label={t("assessment.q.tools.more")}>
          +
        </button>
      </div>
      <p className="mt-3 text-center text-sm text-zinc-500">
        {extra > 0 ? t("assessment.q.tools.extra", { count: extra }) : t("assessment.q.tools.others")}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- analysing

/** A short, honest "working it out": each line is a real step of the sum. */
function Analysing({ answers, onDone }) {
  const { t } = useTranslation();
  const result = useMemo(() => assess(answers), [answers]);
  const lines = [
    t("assessment.working.tools", { count: result.tools }),
    t("assessment.working.customers"),
    t("assessment.working.followUps"),
    t("assessment.working.documents", { count: result.volume }),
    t("assessment.working.payments"),
    t("assessment.working.report"),
  ];
  const [shown, setShown] = useState(reducedMotion() ? lines.length : 1);
  useEffect(() => {
    if (shown >= lines.length) {
      const done = setTimeout(onDone, reducedMotion() ? 300 : 650);
      return () => clearTimeout(done);
    }
    const tick = setTimeout(() => setShown((n) => n + 1), 520);
    return () => clearTimeout(tick);
  }, [shown, lines.length, onDone]);

  return (
    <section className="checkup-in mx-auto max-w-xl rounded-3xl bg-zinc-950 p-7 text-white sm:p-10" aria-live="polite">
      <div className="flex items-center gap-3">
        <span className="checkup-pulse h-3 w-3 rounded-full bg-indigo-400" aria-hidden="true" />
        <h1 className="text-xl font-semibold">{t("assessment.working.title")}</h1>
      </div>
      <ol className="mt-6 space-y-3">
        {lines.slice(0, shown).map((line, i) => {
          const done = i < shown - 1 || shown === lines.length;
          return (
            <li key={line} className="checkup-line flex items-center gap-3 text-[15px]">
              <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${done ? "bg-emerald-500" : "bg-white/10"}`} aria-hidden="true">
                {done ? (
                  <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 text-white" fill="currentColor">
                    <path d="M12.7 4.3a1 1 0 0 1 0 1.4l-5.5 5.5a1 1 0 0 1-1.4 0L3.3 8.7a1 1 0 1 1 1.4-1.4l1.8 1.8 4.8-4.8a1 1 0 0 1 1.4 0Z" />
                  </svg>
                ) : (
                  <span className="checkup-spin h-3 w-3 rounded-full border-2 border-indigo-300 border-t-transparent" />
                )}
              </span>
              <span className={done ? "text-zinc-300" : "text-white"}>{line}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

// ---------------------------------------------------------------- report

const BAND_STYLE = {
  weak: { ring: "#f43f5e", text: "text-rose-600", bg: "bg-rose-50" },
  middle: { ring: "#f59e0b", text: "text-amber-600", bg: "bg-amber-50" },
  strong: { ring: "#10b981", text: "text-emerald-600", bg: "bg-emerald-50" },
};

function useCountUp(target, ms = 1100) {
  const [n, setN] = useState(reducedMotion() ? target : 0);
  useEffect(() => {
    if (reducedMotion()) return setN(target);
    let raf;
    const start = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - start) / ms);
      setN(Math.round(target * (1 - (1 - p) ** 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return n;
}

function ScoreRing({ score }) {
  const { t } = useTranslation();
  const shown = useCountUp(score);
  const style = BAND_STYLE[band(score)];
  const r = 52;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative h-40 w-40 shrink-0">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90" aria-hidden="true">
        <circle cx="60" cy="60" r={r} fill="none" stroke="#f4f4f5" strokeWidth="10" />
        <circle cx="60" cy="60" r={r} fill="none" stroke={style.ring} strokeWidth="10" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - shown / 100)} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl font-semibold tabular-nums tracking-tight text-zinc-900">{shown}</span>
        <span className="text-xs text-zinc-500">{t("assessment.report.outOf")}</span>
      </div>
    </div>
  );
}

function Report({ answers, onRestart }) {
  const { t, i18n } = useTranslation();
  const result = useMemo(() => assess(answers), [answers]);
  const { data: plans } = usePlans();
  const [rate, setRate] = useState(300);
  const rateId = useId();
  const level = band(result.score);
  const style = BAND_STYLE[level];
  const plan = plans?.find((p) => p.key === result.team.plan);
  const cost = planCost(plan, result.team.seats);
  const money = result.totalHours * rate;
  const times = cost ? Math.floor(money / cost) : 0;
  const listOf = (list = []) => {
    const names = list.map((tool) => t(`assessment.toolsInline.${tool}`));
    try {
      return new Intl.ListFormat(i18n.language, { type: "conjunction" }).format(names);
    } catch {
      return names.join(", ");
    }
  };
  // Pipeline and payments have one answer each, so their sentence is written per answer.
  const problem = (area) =>
    area === "pipeline"
      ? t(`assessment.gaps.pipeline.problem.${answers.enquiries}`)
      : area === "payments"
        ? t(`assessment.gaps.payments.problem.${answers.payments}`)
        : t(`assessment.gaps.${area}.problem`, { tools: listOf(answers[area]) });

  return (
    <div className="space-y-6">
      {/* The score and what it means. */}
      <section className="checkup-in card flex flex-col items-center gap-6 p-6 text-center sm:flex-row sm:p-8 sm:text-left">
        <ScoreRing score={result.score} />
        <div className="min-w-0">
          <p className={`text-sm font-semibold ${style.text}`}>{t(`assessment.report.band.${level}.label`)}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-900 sm:text-3xl">{t(`assessment.report.band.${level}.title`)}</h1>
          <p className="mt-2 text-zinc-600">{t(`assessment.report.band.${level}.body`, { name: APP_NAME })}</p>
        </div>
      </section>

      {/* Each area, out of 20, and what juggling tools cost. */}
      <section className="checkup-in card p-6 sm:p-8" style={{ animationDelay: "120ms" }} aria-labelledby="checkup-areas">
        <h2 id="checkup-areas" className="text-lg font-semibold text-zinc-900">{t("assessment.report.areasTitle")}</h2>
        <ul className="mt-5 space-y-4">
          {AREAS.map((area, i) => {
            const value = result.areas[area];
            const share = value / AREA_MAX;
            const color = share >= 0.7 ? "bg-emerald-500" : share >= 0.4 ? "bg-amber-500" : "bg-rose-500";
            return (
              <li key={area}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-medium text-zinc-800">{t(`assessment.areas.${area}`)}</span>
                  <span className="tabular-nums text-zinc-500">{t("assessment.report.points", { value, max: AREA_MAX })}</span>
                </div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-zinc-100">
                  <div className={`checkup-fill h-full rounded-full ${color}`} style={{ width: `${Math.max(share * 100, 3)}%`, animationDelay: `${200 + i * 90}ms` }} />
                </div>
              </li>
            );
          })}
        </ul>
        <div className={`mt-6 flex flex-col gap-3 rounded-2xl p-4 sm:flex-row sm:items-center ${result.toolPenalty ? "bg-amber-50" : "bg-emerald-50"}`}>
          <p className="text-4xl font-semibold tabular-nums tracking-tight text-zinc-900">{result.tools}</p>
          <div className="text-sm">
            <p className="font-semibold text-zinc-900">{t("assessment.report.toolsTitle", { count: result.tools })}</p>
            <p className="mt-0.5 text-zinc-700">
              {result.toolPenalty
                ? t("assessment.report.toolsCost", { points: result.toolPenalty, ok: ASSUMPTIONS.TOOLS_OK })
                : t("assessment.report.toolsFine")}
            </p>
          </div>
        </div>
      </section>

      {/* The biggest gaps, each with the part of YGT that closes it. */}
      <section className="checkup-in" style={{ animationDelay: "220ms" }} aria-labelledby="checkup-gaps">
        <h2 id="checkup-gaps" className="text-lg font-semibold text-zinc-900">
          {result.gaps.length ? t("assessment.report.gapsTitle", { count: result.gaps.length }) : t("assessment.report.noGaps")}
        </h2>
        <ul className="mt-3 grid gap-4 md:grid-cols-3">
          {result.gaps.map((area, i) => (
              <li key={area} className="card flex flex-col overflow-hidden">
                <div className="flex-1 p-5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-rose-600">{t("assessment.report.gap", { n: i + 1 })}</p>
                  <p className="mt-1.5 font-medium leading-snug text-zinc-900">{problem(area)}</p>
                </div>
                <div className="border-t border-zinc-100 bg-zinc-50/70 p-5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">{t("assessment.report.fix", { name: APP_NAME })}</p>
                  <p className="mt-1 text-sm leading-relaxed text-zinc-700">{t(`assessment.gaps.${area}.fix`)}</p>
                </div>
              </li>
          ))}
        </ul>
      </section>

      {/* Time and money back, against what YGT costs. */}
      <section className="checkup-in grid gap-6 overflow-hidden rounded-3xl bg-zinc-50 p-6 ring-1 ring-inset ring-zinc-200/70 sm:p-8 lg:grid-cols-2" style={{ animationDelay: "320ms" }} aria-labelledby="checkup-roi">
        <div>
          <h2 id="checkup-roi" className="text-lg font-semibold text-zinc-900">{t("assessment.report.roiTitle")}</h2>
          <ul className="mt-4 space-y-2 text-sm">
            {Object.entries(result.hours)
              .filter(([, h]) => h >= 0.5)
              .sort((a, b) => b[1] - a[1])
              .map(([key, h]) => (
                <li key={key} className="flex justify-between gap-3 border-b border-zinc-200/70 pb-2">
                  <span className="text-zinc-700">{t(`assessment.hours.${key}`)}</span>
                  <span className="shrink-0 whitespace-nowrap font-medium tabular-nums text-zinc-900">{t("assessment.report.hours", { count: Math.round(h * 2) / 2 })}</span>
                </li>
              ))}
          </ul>
          <div className="mt-6">
            <div className="flex items-baseline justify-between gap-3">
              <label htmlFor={rateId} className="text-sm font-medium text-zinc-700">
                {t("home.savings.rate")}
              </label>
              <span className="shrink-0 whitespace-nowrap text-lg font-semibold tabular-nums text-zinc-900">{rand(rate)}</span>
            </div>
            <input
              id={rateId}
              type="range"
              min={100}
              max={1500}
              step={50}
              value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
              className="savings-range mt-1.5 w-full"
              style={{ "--fill": `${((rate - 100) / 1400) * 100}%` }}
            />
          </div>
        </div>
        <div className="flex flex-col justify-center rounded-2xl bg-zinc-950 p-6 text-white sm:p-8">
          <p className="text-sm text-zinc-400">{t("home.savings.hours")}</p>
          <p className="mt-1 text-5xl font-semibold tabular-nums tracking-tight">
            {result.totalHours}
            <span className="ml-2 text-2xl font-medium text-zinc-400">h</span>
          </p>
          <p className="mt-5 text-sm text-zinc-400">{t("home.savings.money")}</p>
          <p className="savings-money mt-1 text-4xl font-semibold tabular-nums tracking-tight">{rand(money)}</p>
          <div className="mt-5 border-t border-white/10 pt-4 text-sm text-zinc-300">
            {plan && cost ? (
              <>
                <p>
                  {t(plan.per_user ? "assessment.report.planSeats" : "assessment.report.planFlat", {
                    plan: plan.name,
                    seats: result.team.seats,
                    price: rand(cost),
                  })}
                </p>
                {times >= 2 && <p className="mt-1 font-semibold text-white">{t("assessment.report.times", { count: times })}</p>}
              </>
            ) : (
              <p>{t("home.savings.year", { days: Math.round((result.totalHours * 12) / 8) })}</p>
            )}
          </div>
        </div>
        <details className="text-xs text-zinc-500 lg:col-span-2">
          <summary className="cursor-pointer font-medium text-zinc-600">{t("assessment.report.howTitle")}</summary>
          <p className="mt-2 leading-relaxed">
            {t("assessment.report.how", {
              ygt: ASSUMPTIONS.YGT_MINUTES,
              chase: ASSUMPTIONS.CHASE_MINUTES,
              switching: ASSUMPTIONS.SWITCH_HOURS,
              ok: ASSUMPTIONS.TOOLS_OK,
            })}
          </p>
        </details>
      </section>

      {/* The way in, and a person to talk it through with. */}
      <section className="checkup-in grid gap-6 lg:grid-cols-2" style={{ animationDelay: "420ms" }}>
        <div className="flex min-w-0 flex-col justify-center rounded-3xl bg-indigo-600 p-6 text-white sm:p-8">
          <h2 className="text-2xl font-semibold tracking-tight">{t("assessment.report.trialTitle")}</h2>
          <p className="mt-2 text-indigo-100">{t("assessment.report.trialBody", { days: 14 })}</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/register" className="btn !h-auto min-h-11 !whitespace-normal !px-5 py-2 text-center bg-white text-indigo-700 hover:bg-indigo-50">
              {t("home.hero.ctaTrial")}
            </Link>
            <button type="button" onClick={onRestart} className="btn !h-11 !px-5 bg-white/10 text-white hover:bg-white/15">
              {t("assessment.report.again")}
            </button>
          </div>
        </div>
        <Walkthrough answers={answers} result={result} />
      </section>
    </div>
  );
}

/** "Talk me through it": goes to YGT like the contact form, with the result. */
function Walkthrough({ answers, result }) {
  const { t } = useTranslation();
  const [form, setForm] = useState({ name: "", email: "", phone: "", company: "", website: "" });
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");
  const set = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setError("");
    setState("sending");
    // Written in English for YGT's team, whatever language the page is in.
    const message = [
      `Free business check-up: ${result.score}/100`,
      `Industry: ${answers.industry}. Team: ${answers.team}. Quotes and invoices a month: ${result.volume}.`,
      `Tools (${result.tools}): ${result.detected.join(", ")}`,
      `Areas: ${AREAS.map((a) => `${a} ${result.areas[a]}/${AREA_MAX}`).join(", ")}`,
      `Biggest gaps: ${result.gaps.join(", ") || "none"}`,
      `Estimated time back: ${result.totalHours} h a month. Recommended plan: ${result.team.plan}.`,
    ].join("\n");
    try {
      await apiClient.post("/public/contact", { ...form, topic: "sales", message });
      setState("sent");
    } catch (err) {
      setError(errorMessage(err, t("contact.failed")));
      setState("idle");
    }
  }

  if (state === "sent") {
    return (
      <div className="flex min-w-0 flex-col justify-center rounded-3xl bg-emerald-50 p-6 ring-1 ring-inset ring-emerald-200/70 sm:p-8" role="status">
        <p className="text-lg font-semibold text-emerald-900">{t("assessment.talk.sentTitle")}</p>
        <p className="mt-1 text-emerald-900/80">{t("assessment.talk.sentBody", { email: form.email })}</p>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="card min-w-0 p-6 sm:p-8">
      <h2 className="text-lg font-semibold text-zinc-900">{t("assessment.talk.title")}</h2>
      <p className="mt-1 text-sm text-zinc-600">{t("assessment.talk.body")}</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Field label={t("contact.name")}>
          <input className="input" required minLength={2} maxLength={200} autoComplete="name" value={form.name} onChange={set("name")} />
        </Field>
        <Field label={t("contact.email")}>
          <input className="input" required type="email" autoComplete="email" value={form.email} onChange={set("email")} />
        </Field>
        <Field label={t("contact.phone")}>
          <input className="input" type="tel" autoComplete="tel" maxLength={50} value={form.phone} onChange={set("phone")} />
        </Field>
        <Field label={t("contact.company")}>
          <input className="input" autoComplete="organization" maxLength={200} value={form.company} onChange={set("company")} />
        </Field>
      </div>
      <input type="text" name="website" tabIndex={-1} autoComplete="off" value={form.website} onChange={set("website")} className="hidden" aria-hidden="true" />
      <label className="mt-4 flex items-start gap-2.5 text-sm text-zinc-600">
        <input type="checkbox" required className="mt-0.5 h-4 w-4 shrink-0 rounded border-zinc-300 text-indigo-600" />
        <span>{t("assessment.talk.consent", { name: APP_NAME })}</span>
      </label>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <FormError>{error}</FormError>
        <button type="submit" className="btn btn-primary ml-auto" disabled={state === "sending"}>
          {state === "sending" ? t("common.sending") : t("assessment.talk.send")}
        </button>
      </div>
    </form>
  );
}
