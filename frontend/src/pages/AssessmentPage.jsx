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
import { AREA_MAX, AREAS, ASSUMPTIONS, MODEL_VERSION, QUESTIONS, assess, band, recommendPlan, toolsUsed } from "../components/assessment/model";

/*
 * The free business check-up: ten quick questions, a brief "working it
 * out" moment, then a report with an operations score, the biggest gaps,
 * a three-step roadmap, the hours YGT could give back (as a range) and the
 * plan that fits the team and the features they asked for.
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
          <li key={k} className="checkup-in rounded-2xl bg-white/5 p-4 ring-1 ring-inset ring-white/10" style={{ animationDelay: `${160 + i * 70}ms` }}>
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
  // Which way the last move went, so the next card slides in from that side.
  const prevStep = useRef(step);
  const direction = step < prevStep.current ? "back" : "next";
  useEffect(() => {
    prevStep.current = step;
  }, [step]);
  const { t } = useTranslation();
  const q = QUESTIONS[step];
  const value = answers[q.key];
  const detected = toolsUsed(answers);
  const last = step === QUESTIONS.length - 1;

  // The tool count starts from what the earlier answers already named.
  useEffect(() => {
    if (q.kind === "count" && (value == null || value < detected.length)) onAnswer(q.key, Math.max(1, detected.length));
  }, [q, value, detected.length, onAnswer]);

  // Every question moves on by itself once it's answered: one answer at
  // once; several picks, numbers or typing after a pause (the Next button
  // fills meanwhile, and any change starts it again). A new question clears
  // the timer, so one started before Back can't jump forward.
  const advance = useRef(null);
  const nextRef = useRef(null);
  nextRef.current = () => (last ? onDone() : onStep(step + 1));
  const [countdown, setCountdown] = useState(null);
  const later = (ms) => {
    clearTimeout(advance.current);
    advance.current = setTimeout(() => nextRef.current(), ms);
    setCountdown(ms >= 600 ? { ms, id: Date.now() } : null);
  };
  const cancel = () => {
    clearTimeout(advance.current);
    setCountdown(null);
  };
  useEffect(
    () => () => {
      clearTimeout(advance.current);
      setCountdown(null);
    },
    [step]
  );
  const next = () => {
    cancel();
    nextRef.current();
  };
  const described = answers.industry !== "other" || answers.industryDetail?.trim().length >= 2;
  const ready =
    q.kind === "profile"
      ? answers.industry != null && described && answers.team != null
      : q.kind === "multi"
        ? value?.length > 0
        : q.kind === "volumes"
          ? true
          : q.kind === "count"
            ? value != null && answers.connect != null
            : value != null;

  // What the person has answered on this question. A change to it (not
  // arriving at it, say after Back) starts the move on, once it's complete.
  const answered = JSON.stringify(
    q.kind === "profile"
      ? [answers.industry, answers.industryDetail, answers.team]
      : q.kind === "volumes"
        ? [answers.quotes, answers.invoices]
        : q.kind === "count"
          ? [value, answers.connect]
          : q.kind === "multi"
            ? value
            : null
  );
  const seen = useRef({ step, answered });
  // The sliders wait until both are set, so quotes can't move on before
  // invoices get a turn.
  const touched = useRef(new Set());
  useEffect(() => {
    if (seen.current.step !== step) {
      seen.current = { step, answered };
      touched.current = new Set();
      return;
    }
    if (seen.current.answered === answered) return;
    seen.current.answered = answered;
    const waiting = q.kind === "volumes" && touched.current.size < q.fields.length;
    // The last question is theirs to submit, so it never finishes by itself.
    if (ready && !waiting && !last) later(1500);
    else cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, answered, ready]);

  function pick(option) {
    if (q.kind === "multi") {
      const list = value ?? [];
      onAnswer(q.key, list.includes(option) ? list.filter((v) => v !== option) : [...list, option]);
      return;
    }
    onAnswer(q.key, option);
    // One answer moves on by itself, after a beat to see it land.
    later(reducedMotion() ? 0 : 280);
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
        <span key={detected.length} className={`mr-1 text-xs font-semibold uppercase tracking-wide text-zinc-400 ${detected.length ? "checkup-bump" : ""}`}>
          {t("assessment.spotted", { count: detected.length })}
        </span>
        {detected.map((tool) => (
          <span key={tool} className="checkup-chip rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-900 ring-1 ring-inset ring-amber-600/20">
            {t(`assessment.tools.${tool}`)}
          </span>
        ))}
      </div>

      <div key={q.key} className={`checkup-q-${direction} mt-4 rounded-3xl bg-white p-5 shadow-pop ring-1 ring-zinc-900/5 sm:p-8`}>
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">{t(`assessment.q.${q.key}.topic`)}</p>
        <h1 id="checkup-q" className="mt-1.5 text-2xl font-semibold tracking-tight text-zinc-900 sm:text-3xl">
          {t(`assessment.q.${q.key}.title`)}
        </h1>
        <p className="mt-1.5 text-zinc-600">{t(`assessment.q.${q.key}.hint`, { defaultValue: q.kind === "multi" ? t("assessment.pickAll") : "" })}</p>

        <div className="mt-6">
          {q.kind === "profile" ? (
            <Profile q={q} answers={answers} onAnswer={onAnswer} />
          ) : q.kind === "single" || q.kind === "multi" ? (
            <Options q={q} value={value} onPick={pick} />
          ) : q.kind === "volumes" ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {q.fields.map((field) => (
                <Volume key={field} q={q} field={field} value={answers[field] ?? 0} onChange={(v) => {
                    touched.current.add(field);
                    onAnswer(field, v);
                  }}
                />
              ))}
            </div>
          ) : (
            <ToolCount q={q} value={value ?? 1} detected={detected} connect={answers.connect} onChange={(v) => onAnswer(q.key, v)} onConnect={(v) => onAnswer("connect", v)} />
          )}
        </div>

        <div className="mt-8 flex items-center justify-between gap-3">
          <button type="button" className="btn btn-secondary" onClick={() => onStep(step - 1)} disabled={step === 0}>
            {t("assessment.back")}
          </button>
          {(q.kind !== "single" || value != null) && (
            <button type="button" className="btn btn-primary relative overflow-hidden" onClick={next} disabled={!ready}>
              {/* Fills while the question waits to move on by itself. */}
              {countdown && <span key={countdown.id} className="checkup-countdown" style={{ "--ms": `${countdown.ms}ms` }} aria-hidden="true" />}
              <span className="relative">{last ? t("assessment.finish") : t("assessment.next")}</span>
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

/** Business type (photo cards) and the people who'd use YGT, on one card. */
function Profile({ q, answers, onAnswer }) {
  const { t } = useTranslation();
  const detailId = useId();
  const other = answers.industry === "other";
  return (
    <div className="space-y-6">
      <Options q={{ key: "industry", kind: "single", options: q.industry }} value={answers.industry} onPick={(v) => onAnswer("industry", v)} />
      {/* In their own words: required for "Something else", optional otherwise. */}
      {answers.industry != null && (
        <div className="checkup-in">
          <label htmlFor={detailId} className="font-medium text-zinc-900">
            {t(other ? "assessment.q.profile.describeOther" : "assessment.q.profile.describe")}
          </label>
          <input
            id={detailId}
            className="input mt-2"
            maxLength={120}
            required={other}
            autoFocus={other}
            placeholder={t("assessment.q.profile.describePlaceholder")}
            value={answers.industryDetail ?? ""}
            onChange={(e) => onAnswer("industryDetail", e.target.value)}
          />
        </div>
      )}
      <div>
        <p className="font-medium text-zinc-900">{t("assessment.q.profile.team")}</p>
        <p className="mt-0.5 text-sm text-zinc-500">{t("assessment.q.profile.teamHint")}</p>
        <div className="mt-3">
          <Options q={{ key: "team", kind: "single", options: q.team }} value={answers.team} onPick={(v) => onAnswer("team", v)} />
        </div>
      </div>
    </div>
  );
}

function Options({ q, value, onPick }) {
  const { t } = useTranslation();
  const multi = q.kind === "multi";
  const photo = (key) => PEOPLE.find((p) => p.key === key)?.photo;
  const label = (option) =>
    q.key === "industry"
      ? option === "other"
        ? t("assessment.q.profile.other")
        : t(`home.people.${option}.label`)
      : t(`assessment.q.${q.key}.${q.labels ?? "options"}.${option}`);
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
                  <svg viewBox="0 0 16 16" className="checkup-tick h-3.5 w-3.5 text-white" fill="currentColor">
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

/** One count, starting at 0 so nobody accepts a number we suggested. */
function Volume({ q, field, value, onChange }) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div className="rounded-2xl bg-zinc-50 p-5 ring-1 ring-inset ring-zinc-200/70">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-sm font-medium text-zinc-700">
          {t(`assessment.q.volume.${field}`)}
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

function ToolCount({ q, value, detected, connect, onChange, onConnect }) {
  const { t } = useTranslation();
  const [roll, setRoll] = useState(null);
  const step = (next) => {
    setRoll(next > value ? "up" : "down");
    onChange(next);
  };
  // The answers already named these, so the count can't go below them.
  const min = Math.max(q.min, detected.length);
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
        <button type="button" className="btn btn-secondary !h-12 !w-12 !p-0 text-xl" onClick={() => step(Math.max(min, value - 1))} disabled={value <= min} aria-label={t("assessment.q.tools.less")}>
          −
        </button>
        <div className="min-w-24 text-center">
          <p className="overflow-hidden text-5xl font-semibold tabular-nums tracking-tight text-zinc-900" aria-live="polite">
            <span key={value} className={`inline-block ${roll ? `checkup-roll-${roll}` : ""}`}>
              {value}
              {value >= q.max ? "+" : ""}
            </span>
          </p>
          <p className="text-sm text-zinc-500">{t("assessment.q.tools.unit", { count: value })}</p>
        </div>
        <button type="button" className="btn btn-secondary !h-12 !w-12 !p-0 text-xl" onClick={() => step(Math.min(q.max, value + 1))} disabled={value >= q.max} aria-label={t("assessment.q.tools.more")}>
          +
        </button>
      </div>
      <p className="mt-3 text-center text-sm text-zinc-500">
        {extra > 0 ? t("assessment.q.tools.extra", { count: extra }) : t("assessment.q.tools.others")}
      </p>
      {/* More tools aren't a problem by themselves; copying between them by hand is. */}
      <div className="mt-8 border-t border-zinc-100 pt-6">
        <p className="font-medium text-zinc-900">{t("assessment.q.tools.connect")}</p>
        <div className="mt-3">
          <Options q={{ key: "tools", kind: "single", options: q.connect, labels: "connectOptions" }} value={connect} onPick={onConnect} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- analysing

/** A brief, honest "working it out" (under a second): each line is a real
    step of the sum. The sum itself is instant; this just shows its steps. */
function Analysing({ answers, onDone }) {
  const { t } = useTranslation();
  const result = useMemo(() => assess(answers), [answers]);
  const lines = [
    t("assessment.working.tools", { count: result.tools }),
    t("assessment.working.customers"),
    t("assessment.working.followUps"),
    t("assessment.working.documents", { count: result.quotes + result.invoices }),
    t("assessment.working.payments"),
    t("assessment.working.report"),
  ];
  const [shown, setShown] = useState(reducedMotion() ? lines.length : 1);
  useEffect(() => {
    if (shown >= lines.length) {
      const done = setTimeout(onDone, reducedMotion() ? 200 : 300);
      return () => clearTimeout(done);
    }
    const tick = setTimeout(() => setShown((n) => n + 1), 110);
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
                  <svg viewBox="0 0 16 16" className="checkup-tick h-3.5 w-3.5 text-white" fill="currentColor">
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
  attention: { ring: "#f43f5e", text: "text-rose-600" },
  progress: { ring: "#f59e0b", text: "text-amber-600" },
  organised: { ring: "#10b981", text: "text-emerald-600" },
  high: { ring: "#059669", text: "text-emerald-700" },
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
    <div className={`relative h-40 w-40 shrink-0 ${shown === score && score > 0 ? "checkup-settle" : ""}`}>
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

// The feature on the About page that each roadmap step leads to.
const FEATURE_FOR = { customers: "sales", pipeline: "sales", tasks: "sales", documents: "billing", payments: "billing" };

// To the half hour, but never down to 0 for time that is still spent.
const hoursText = (t, h) => t("assessment.report.hours", { count: h > 0 ? Math.max(0.5, Math.round(h * 2) / 2) : 0 });

function Report({ answers, onRestart }) {
  const { t, i18n } = useTranslation();
  const result = useMemo(() => assess(answers), [answers]);
  const { data: plans } = usePlans();
  const [rate, setRate] = useState(300);
  const rateId = useId();
  const level = band(result.score);
  const style = BAND_STYLE[level];
  const pick = useMemo(() => recommendPlan(plans, answers.needs, result.team.seats), [plans, answers.needs, result.team.seats]);
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
  const gain = ([, line]) => line.now - line.ygt;
  const lines = Object.entries(result.sheet)
    .filter((entry) => gain(entry) >= 0.5)
    .sort((a, b) => gain(b) - gain(a));
  // The hours count up with the score: the moment the report lands.
  const low = useCountUp(result.hours.low, 900);
  const high = useCountUp(result.hours.high, 900);
  const range = (low, high, fmt) => (low === high ? fmt(high) : t("assessment.report.range", { low: fmt(low), high: fmt(high) }));

  return (
    <div className="space-y-6">
      {/* The score and what it means: how organised these processes are, not how good the business is. */}
      <section className="checkup-in card flex flex-col items-center gap-6 p-6 text-center sm:flex-row sm:p-8 sm:text-left">
        <ScoreRing score={result.score} />
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{t("assessment.report.scoreName")}</p>
          <p className={`mt-1 text-sm font-semibold ${style.text}`}>{t(`assessment.report.band.${level}.label`)}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-900 sm:text-3xl">{t(`assessment.report.band.${level}.title`)}</h1>
          <p className="mt-2 text-zinc-600">{t(`assessment.report.band.${level}.body`, { name: APP_NAME })}</p>
          <p className="mt-2 text-xs text-zinc-500">{t("assessment.report.scoreNote")}</p>
        </div>
      </section>

      {/* Each area, out of 20, and what loose tools cost. */}
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
        {/* How the five areas become the score, so the sum can be checked. */}
        <dl className="mt-6 grid grid-cols-3 gap-2 rounded-2xl bg-zinc-50 p-3 text-center text-sm ring-1 ring-inset ring-zinc-200/70">
          <div>
            <dt className="text-zinc-500">{t("assessment.report.sumAreas")}</dt>
            <dd className="mt-0.5 font-semibold tabular-nums text-zinc-900">{result.areaTotal}/100</dd>
          </div>
          <div>
            <dt className="text-zinc-500">{t("assessment.report.sumTools")}</dt>
            <dd className="mt-0.5 font-semibold tabular-nums text-zinc-900">{result.toolPenalty ? `−${result.toolPenalty}` : "0"}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">{t("assessment.report.sumScore")}</dt>
            <dd className="mt-0.5 font-semibold tabular-nums text-zinc-900">{result.score}/100</dd>
          </div>
        </dl>
        <div className={`mt-4 flex flex-col gap-3 rounded-2xl p-4 sm:flex-row sm:items-center ${result.toolPenalty ? "bg-amber-50" : "bg-emerald-50"}`}>
          <p className="text-4xl font-semibold tabular-nums tracking-tight text-zinc-900">{result.tools}</p>
          <div className="text-sm">
            <p className="font-semibold text-zinc-900">{t("assessment.report.toolsTitle", { count: result.tools })}</p>
            <p className="mt-0.5 text-zinc-700">
              {result.toolPenalty
                ? t(`assessment.report.toolsCost.${answers.connect ?? "unsure"}`, { loose: result.loose, points: result.toolPenalty, ok: ASSUMPTIONS.TOOLS_OK })
                : answers.connect === "auto"
                  ? t("assessment.report.toolsConnected")
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
            <li key={area} className="checkup-in card flex flex-col overflow-hidden" style={{ animationDelay: `${260 + i * 70}ms` }}>
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

      {/* A short plan they can follow, whether or not they sign up. */}
      {result.gaps.length > 0 && (
        <section className="checkup-in card p-6 sm:p-8" style={{ animationDelay: "270ms" }} aria-labelledby="checkup-roadmap">
          <h2 id="checkup-roadmap" className="text-lg font-semibold text-zinc-900">{t("assessment.roadmap.title", { count: result.gaps.length })}</h2>
          <ol className="mt-4 grid gap-4 md:grid-cols-3">
            {result.gaps.map((area, i) => (
              <li key={area} className="flex gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold text-white">{i + 1}</span>
                <div className="min-w-0">
                  <p className="font-medium text-zinc-900">{t(`assessment.roadmap.${area}.title`)}</p>
                  <p className="mt-1 text-sm leading-relaxed text-zinc-600">{t(`assessment.roadmap.${area}.body`)}</p>
                  <Link to={`/about#feature-${FEATURE_FOR[area]}`} className="mt-1.5 inline-block text-sm font-medium text-indigo-700 hover:text-indigo-900">
                    {t("assessment.roadmap.link", { name: APP_NAME })} →
                  </Link>
                </div>
              </li>
            ))}
          </ol>
          <p className="mt-5 text-sm font-medium text-indigo-700">{t("assessment.roadmap.footer")}</p>
        </section>
      )}

      {/* Admin time now and with YGT, as a range, and what that time could be worth. */}
      <section className="checkup-in grid gap-6 overflow-hidden rounded-3xl bg-zinc-50 p-6 ring-1 ring-inset ring-zinc-200/70 sm:p-8 lg:grid-cols-2" style={{ animationDelay: "320ms" }} aria-labelledby="checkup-roi">
        <div className="min-w-0">
          <h2 id="checkup-roi" className="text-lg font-semibold text-zinc-900">{t("assessment.report.roiTitle")}</h2>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-2xl bg-white p-3 ring-1 ring-inset ring-zinc-200/70">
              <dt className="text-zinc-500">{t("assessment.report.now")}</dt>
              <dd className="mt-0.5 text-xl font-semibold tabular-nums text-zinc-900">{hoursText(t, result.hoursNow)}</dd>
            </div>
            <div className="rounded-2xl bg-white p-3 ring-1 ring-inset ring-zinc-200/70">
              <dt className="text-zinc-500">{t("assessment.report.withYgt", { name: APP_NAME })}</dt>
              <dd className="mt-0.5 text-xl font-semibold tabular-nums text-zinc-900">{hoursText(t, result.hoursYgt)}</dd>
            </div>
          </dl>
          <ul className="mt-4 space-y-2 text-sm">
            {lines.map(([key, line]) => (
              <li key={key} className="flex justify-between gap-3 border-b border-zinc-200/70 pb-2">
                <span className="min-w-0 text-zinc-700">{t(`assessment.hours.${key}`)}</span>
                <span className="shrink-0 whitespace-nowrap tabular-nums text-zinc-500">
                  {hoursText(t, line.now)} → <span className="font-medium text-zinc-900">{hoursText(t, line.ygt)}</span>
                </span>
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
        <div className="flex min-w-0 flex-col justify-center rounded-2xl bg-zinc-950 p-6 text-white sm:p-8">
          <p className="text-sm text-zinc-400">{t("assessment.report.freed")}</p>
          <p className="mt-1 text-4xl font-semibold tabular-nums tracking-tight sm:text-5xl">
            {range(low, high, (n) => n)}
            <span className="ml-1.5 text-2xl font-medium text-zinc-300">h</span>
            <span className="ml-2 text-xl font-medium text-zinc-400">{t("assessment.report.perMonth")}</span>
          </p>
          <p className="mt-5 text-sm text-zinc-400">{t("assessment.report.worth")}</p>
          <p className="savings-money mt-1 text-3xl font-semibold tabular-nums tracking-tight sm:text-4xl">{range(low * rate, high * rate, rand)}</p>
          {/* Where each end of the range comes from. */}
          <ul className="mt-4 space-y-1 border-t border-white/10 pt-3 text-xs leading-relaxed text-zinc-300">
            <li>{t("assessment.report.rangeHigh", { hours: result.hours.high, name: APP_NAME })}</li>
            {result.hours.low !== result.hours.high && (
              <li>{t("assessment.report.rangeLow", { hours: result.hours.low, minutes: ASSUMPTIONS.LOW_YGT_MINUTES })}</li>
            )}
          </ul>
          <p className="mt-3 text-xs leading-relaxed text-zinc-400">{t("assessment.report.worthNote")}</p>
        </div>
        <details className="text-xs text-zinc-500 lg:col-span-2">
          <summary className="cursor-pointer font-medium text-zinc-600">{t("assessment.report.howTitle")}</summary>
          <p className="mt-2 leading-relaxed">
            {t("assessment.report.how", {
              ygt: ASSUMPTIONS.YGT_MINUTES,
              lowYgt: ASSUMPTIONS.LOW_YGT_MINUTES,
              chase: ASSUMPTIONS.CHASE_MINUTES,
              switching: ASSUMPTIONS.SWITCH_HOURS,
              ok: ASSUMPTIONS.TOOLS_OK,
              name: APP_NAME,
            })}
          </p>
        </details>
      </section>

      {/* The plan that fits: room for the team, and every feature they asked for. */}
      {pick && (
        <section className="checkup-in card p-6 sm:p-8" style={{ animationDelay: "370ms" }} aria-labelledby="checkup-plan">
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">{t("assessment.plan.eyebrow")}</p>
          <h2 id="checkup-plan" className="mt-1 text-2xl font-semibold tracking-tight text-zinc-900">{t("assessment.plan.title", { plan: pick.plan.name })}</h2>
          <p className="mt-1 text-zinc-600">
            {t(pick.plan.per_user ? "assessment.plan.priceSeats" : "assessment.plan.priceFlat", { count: result.team.seats, price: rand(pick.cost) })}
          </p>
          {/* Why: the team, the features they picked, then what every plan has. */}
          <dl className="mt-4 space-y-3 text-sm text-zinc-700">
            <div>
              <dt className="font-semibold text-zinc-900">{t("assessment.plan.teamFit")}</dt>
              <dd className="mt-1 flex gap-2">
                <Tick />
                {t(pick.plan.per_user ? "assessment.plan.whySeats" : "assessment.plan.whyFlat", { count: result.team.seats, max: pick.plan.max_users })}
              </dd>
            </div>
            {pick.wanted.length > 0 && (
              <div>
                <dt className="font-semibold text-zinc-900">{t("assessment.plan.featureFit")}</dt>
                {pick.wanted.map((feature) => (
                  <dd key={feature} className="mt-1 flex gap-2">
                    <Tick />
                    {t(`assessment.plan.features.${feature}`)}
                  </dd>
                ))}
              </div>
            )}
            <div>
              <dt className="font-semibold text-zinc-900">{t("assessment.plan.included")}</dt>
              <dd className="mt-1 flex gap-2">
                <Tick />
                {t("assessment.plan.whyAll")}
              </dd>
            </div>
          </dl>
          <Link to="/about#about-pricing" className="mt-4 inline-block text-sm font-medium text-indigo-700 hover:text-indigo-900">
            {t("assessment.plan.compare")}
          </Link>
        </section>
      )}

      {/* The way in, and a person to talk it through with. */}
      <section className="checkup-in grid gap-6 lg:grid-cols-2" style={{ animationDelay: "420ms" }}>
        <div className="flex min-w-0 flex-col justify-center rounded-3xl bg-indigo-600 p-6 text-white sm:p-8">
          <h2 className="text-2xl font-semibold tracking-tight">{t("assessment.report.trialTitle")}</h2>
          <p className="mt-2 text-indigo-100">{t("assessment.report.trialBody", { days: 14, name: APP_NAME })}</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/register" className="btn !h-auto min-h-11 !whitespace-normal !px-5 py-2 text-center bg-white text-indigo-700 hover:bg-indigo-50">
              {t("home.hero.ctaTrial")}
            </Link>
            <button type="button" onClick={onRestart} className="btn !h-11 !px-5 bg-white/10 text-white hover:bg-white/15">
              {t("assessment.report.again")}
            </button>
          </div>
        </div>
        <Walkthrough answers={answers} result={result} plan={pick?.plan} />
      </section>
    </div>
  );
}

function Tick() {
  return (
    <svg viewBox="0 0 16 16" className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" fill="currentColor" aria-hidden="true">
      <path d="M12.7 4.3a1 1 0 0 1 0 1.4l-5.5 5.5a1 1 0 0 1-1.4 0L3.3 8.7a1 1 0 1 1 1.4-1.4l1.8 1.8 4.8-4.8a1 1 0 0 1 1.4 0Z" />
    </svg>
  );
}

/** "Talk me through it": goes to YGT like the contact form, with the result. */
function Walkthrough({ answers, result, plan }) {
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
      `Free business check-up (rules v${MODEL_VERSION}): operations score ${result.score}/100`,
      `Industry: ${answers.industry}${answers.industryDetail?.trim() ? ` (${answers.industryDetail.trim()})` : ""}. People handling admin: ${answers.team}. A month: ${result.quotes} quotes, ${result.invoices} invoices.`,
      `Tools (${result.tools}, ${answers.connect ?? "not said"}): ${result.detected.join(", ")}`,
      `Areas: ${AREAS.map((a) => `${a} ${result.areas[a]}/${AREA_MAX}`).join(", ")}`,
      `Biggest gaps: ${result.gaps.join(", ") || "none"}`,
      `Wants: ${answers.needs?.join(", ") || "not said"}`,
      `Estimated time freed: ${result.hours.low}-${result.hours.high} h a month. Recommended plan: ${plan?.name ?? "unknown"}.`,
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
      <div className="checkup-in flex min-w-0 flex-col justify-center rounded-3xl bg-emerald-50 p-6 ring-1 ring-inset ring-emerald-200/70 sm:p-8" role="status">
        <svg viewBox="0 0 24 24" className="h-10 w-10 text-emerald-600" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10.5" className="opacity-20" />
          <path d="M7 12.5l3.2 3.2L17 9" className="checkup-draw" />
        </svg>
        <p className="mt-3 text-lg font-semibold text-emerald-900">{t("assessment.talk.sentTitle")}</p>
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
        <span>
          {t("assessment.talk.consent", { name: APP_NAME })}{" "}
          <Link to="/privacy" target="_blank" className="font-medium text-indigo-700 underline-offset-2 hover:underline">
            {t("assessment.talk.privacy")}
          </Link>
        </span>
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
