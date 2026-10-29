import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

/*
 * What YGT gives back, in the visitor's own numbers. The figures follow
 * the sliders straight away (no count-up: the person is dragging, and a
 * number that lags their hand reads as broken). The assumption is printed
 * under the result, so it is an estimate and says so.
 */

const MINUTES_PER_DOC = 15;
const rand = (n) => `R ${Math.round(n).toLocaleString("en-ZA").replace(/,/g, " ")}`;

function Slider({ label, value, display, onChange, min, max, step }) {
  const id = useId();
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-sm font-medium text-zinc-700">
          {label}
        </label>
        <span className="text-lg font-semibold tabular-nums text-zinc-900">{display}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="savings-range mt-1.5 w-full"
        style={{ "--fill": `${((value - min) / (max - min)) * 100}%` }}
      />
    </div>
  );
}

export default function HomeSavings() {
  const { t } = useTranslation();
  const [docs, setDocs] = useState(40);
  const [rate, setRate] = useState(300);
  const hours = (docs * MINUTES_PER_DOC) / 60;
  const money = hours * rate;
  const days = Math.round((hours * 12) / 8);

  return (
    <section className="py-12" aria-labelledby="home-savings">
      <div className="reveal grid gap-8 overflow-hidden rounded-3xl bg-zinc-50 p-6 ring-1 ring-inset ring-zinc-200/70 sm:p-10 lg:grid-cols-2 lg:gap-x-12 lg:gap-y-6">
        <div>
          <p className="text-sm font-semibold text-indigo-600">{t("home.savings.title")}</p>
          <h2 id="home-savings" className="mt-2 text-3xl font-semibold tracking-tight text-zinc-900">
            {t("home.savings.question", { hours: Number.isInteger(hours) ? hours : hours.toFixed(1) })}
          </h2>
          <p className="mt-2 text-zinc-600">{t("home.savings.explain")}</p>
          <div className="mt-8 space-y-7">
            <Slider label={t("home.savings.docs")} value={docs} display={docs} onChange={setDocs} min={5} max={300} step={5} />
            <Slider label={t("home.savings.rate")} value={rate} display={rand(rate)} onChange={setRate} min={100} max={1500} step={50} />
          </div>
        </div>

        <div className="flex flex-col justify-center rounded-2xl bg-zinc-950 p-6 text-white sm:p-8">
          <p className="text-sm text-zinc-400">{t("home.savings.hours")}</p>
          <p className="mt-1 text-5xl font-semibold tracking-tight tabular-nums sm:text-6xl">
            {Number.isInteger(hours) ? hours : hours.toFixed(1)}
            <span className="ml-2 text-2xl font-medium text-zinc-400">h</span>
          </p>
          <p className="mt-6 text-sm text-zinc-400">{t("home.savings.money")}</p>
          <p className="savings-money mt-1 text-4xl font-semibold tracking-tight tabular-nums sm:text-5xl">{rand(money)}</p>
          <p className="mt-6 border-t border-white/10 pt-4 text-sm text-zinc-300">{t("home.savings.year", { days })}</p>
          {/* A rough number here; the check-up works out theirs. */}
          <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2">
            <Link to="/assessment" className="btn !h-11 !px-5 bg-white text-zinc-900 hover:bg-zinc-100">
              {t("home.checkup.cta")}
            </Link>
            <span className="text-sm text-zinc-400">{t("home.checkup.meta")}</span>
          </div>
        </div>
        <p className="text-xs text-zinc-500 lg:col-span-2">{t("home.savings.note", { minutes: MINUTES_PER_DOC })}</p>
      </div>
    </section>
  );
}
