import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { APP_NAME, BrandMark } from "../Brand";
import { EASE_OUT, prefersReducedMotion } from "../../utils/motion";

/*
 * The home page's hero: a desk's worth of scattered admin (a WhatsApp,
 * a sticky note, a spreadsheet, an email thread, a till slip) gets pulled
 * into one YGT screen, where each becomes a tidy, finished row. Then the
 * mess comes back and it happens again.
 *
 * Motion budget: marketing/explanatory tier, seen once per visit, so this
 * is where the page's boldness is spent. The clutter flies with WAAPI on
 * transform/opacity, set on each element directly; the window and its
 * rows are CSS transitions keyed on data-phase. Reduced motion shows the
 * finished screen, still. The loop pauses while the scene is off screen.
 *
 * "Before / With YGT" names the two states as they play; picking one
 * stops the loop there, so a visitor can compare at their own pace.
 */

const MESS_MS = 4200;
const SORTED_MS = 7500;
const EASE_IN_OUT = "cubic-bezier(0.77, 0, 0.175, 1)"; // same as --ease-in-out
const SAVED_MINUTES = 380;

// Where each piece of clutter lies on the desk, and its tilt.
const CLUTTER = [
  { key: "whatsapp", place: "left-[3%] top-[7%] w-[54%] sm:w-[46%]", tilt: -5 },
  { key: "note", place: "right-[4%] top-[5%] w-[34%] sm:w-[28%]", tilt: 6 },
  { key: "sheet", place: "left-[4%] top-[47%] w-[60%] sm:w-[44%]", tilt: 3 },
  { key: "email", place: "right-[3%] top-[38%] w-[48%] sm:w-[42%]", tilt: -4 },
  { key: "receipt", place: "left-[38%] bottom-[19%] w-[30%] sm:w-[24%]", tilt: -7 },
];

const ROWS = [
  { key: "quote", tone: "bg-indigo-100 text-indigo-600", value: "R 1 840,00" },
  { key: "followUp", tone: "bg-amber-100 text-amber-600", valueKey: "followUpWhen" },
  { key: "paid", tone: "bg-emerald-100 text-emerald-600", value: "R 14 605,00" },
  { key: "reminders", tone: "bg-sky-100 text-sky-600", valueKey: "auto" },
];

function Tick() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="h-3.5 w-3.5">
      <path d="M3.5 8.5 6.5 11.5 12.5 4.5" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Clutter({ kind, t }) {
  switch (kind) {
    case "whatsapp":
      return (
        <div className="rounded-2xl rounded-tl-md bg-[#d9fdd3] px-3 py-2 shadow-[0_6px_20px_-6px_rgb(0_0_0/0.25)]">
          <p className="text-[11px] font-semibold text-emerald-700">{t("home.scene.whatsappFrom")}</p>
          <p className="text-[13px] leading-snug text-zinc-800">{t("home.scene.whatsapp")}</p>
          <p className="mt-0.5 text-right text-[10px] text-zinc-500">09:14 ✓✓</p>
        </div>
      );
    case "note":
      return (
        <div className="bg-amber-200 px-3 pb-4 pt-3 shadow-[0_8px_18px_-8px_rgb(120_80_0/0.45)]">
          <p className="text-[14px] font-semibold leading-snug text-amber-950 underline decoration-amber-500 decoration-2 underline-offset-4">
            {t("home.scene.note")}
          </p>
        </div>
      );
    case "sheet":
      return (
        <div className="flex items-center gap-2.5 rounded-xl bg-white px-3 py-2.5 shadow-[0_6px_20px_-6px_rgb(0_0_0/0.25)] ring-1 ring-zinc-900/5">
          <span className="grid h-8 w-7 shrink-0 grid-cols-2 gap-px overflow-hidden rounded-[4px] bg-emerald-600 p-[3px]">
            {Array.from({ length: 6 }, (_, i) => (
              <span key={i} className="bg-white/80" />
            ))}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[12.5px] font-medium text-zinc-800">{t("home.scene.sheet")}</span>
            <span className="block text-[10.5px] text-zinc-400">{t("home.scene.sheetMeta")}</span>
          </span>
        </div>
      );
    case "email":
      return (
        <div className="rounded-xl bg-white px-3 py-2.5 shadow-[0_6px_20px_-6px_rgb(0_0_0/0.25)] ring-1 ring-zinc-900/5">
          <p className="flex items-center gap-1.5 text-[11px] text-zinc-500">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} className="h-3.5 w-3.5" aria-hidden="true">
              <rect x="2" y="3.5" width="12" height="9" rx="1.5" />
              <path d="m2.5 4.5 5.5 4 5.5-4" />
            </svg>
            {t("home.scene.emailFrom")}
            <span className="ml-auto rounded-full bg-rose-500 px-1.5 text-[10px] font-semibold text-white">7</span>
          </p>
          <p className="mt-1 truncate text-[12.5px] font-medium text-zinc-800">{t("home.scene.email")}</p>
        </div>
      );
    default:
      return (
        <div className="scene-receipt bg-white px-3 pb-5 pt-2.5 shadow-[0_6px_16px_-6px_rgb(0_0_0/0.3)]">
          <p className="text-[10px] uppercase text-zinc-400">{t("home.scene.receipt")}</p>
          <p className="mt-1 border-b border-dashed border-zinc-300 pb-1 text-[13px] font-semibold tabular-nums text-zinc-800">R 1 250,00</p>
          <p className="mt-1 -rotate-3 text-[12px] font-semibold text-rose-600">{t("home.scene.receiptNote")}</p>
        </div>
      );
  }
}

export default function HomeScene() {
  const { t } = useTranslation();
  const rootRef = useRef(null);
  const windowRef = useRef(null);
  const clutterRefs = useRef([]);
  const [reduce] = useState(prefersReducedMotion);
  const [phase, setPhase] = useState(reduce ? "sorted" : "mess");
  const [onScreen, setOnScreen] = useState(true);
  const [picked, setPicked] = useState(false);
  const [saved, setSaved] = useState(reduce ? SAVED_MINUTES : 0);

  // Only loop while someone can see it.
  useEffect(() => {
    const el = rootRef.current;
    if (!el || !("IntersectionObserver" in window)) return undefined;
    const io = new IntersectionObserver(([entry]) => setOnScreen(entry.isIntersecting));
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (reduce || !onScreen || picked) return undefined;
    const timer = setTimeout(() => setPhase((p) => (p === "mess" ? "sorted" : "mess")), phase === "mess" ? MESS_MS : SORTED_MS);
    return () => clearTimeout(timer);
  }, [phase, onScreen, reduce, picked]);

  // The clutter: lands on the desk, then flies into the window.
  useLayoutEffect(() => {
    if (reduce) return undefined;
    const items = clutterRefs.current.filter(Boolean);
    items.forEach((el) => el.getAnimations().forEach((a) => a.cancel()));
    if (phase === "mess") {
      items.forEach((el, i) =>
        el.animate(
          [
            { opacity: 0, transform: "translateY(14px) scale(0.94)" },
            { opacity: 1, transform: "none" },
          ],
          { duration: 800, delay: 150 + i * 140, easing: EASE_OUT, fill: "backwards" }
        )
      );
      return undefined;
    }
    const target = windowRef.current.getBoundingClientRect();
    const cx = target.left + target.width / 2;
    const cy = target.top + target.height / 2;
    items.forEach((el, i) => {
      const r = el.getBoundingClientRect();
      const dx = cx - (r.left + r.width / 2);
      const dy = cy - (r.top + r.height / 2);
      el.animate(
        [
          { opacity: 1, transform: "none" },
          { opacity: 1, transform: `translate(${dx * 0.85}px, ${dy * 0.85}px) scale(0.55)`, offset: 0.8 },
          { opacity: 0, transform: `translate(${dx}px, ${dy}px) scale(0.4)` },
        ],
        { duration: 1300, delay: i * 160, easing: EASE_IN_OUT, fill: "forwards" }
      );
    });
    return undefined;
  }, [phase, reduce]);

  // "Time saved" counts up once the rows have landed.
  useEffect(() => {
    if (reduce) return undefined;
    if (phase !== "sorted") {
      setSaved(0);
      return undefined;
    }
    let raf;
    const begin = performance.now() + 2400;
    const run = (now) => {
      const p = Math.min(Math.max((now - begin) / 2200, 0), 1);
      setSaved(Math.round(SAVED_MINUTES * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(run);
    };
    raf = requestAnimationFrame(run);
    return () => cancelAnimationFrame(raf);
  }, [phase, reduce]);

  return (
    <div
      ref={rootRef}
      data-phase={phase}
      className="scene relative h-full w-full overflow-hidden bg-gradient-to-br from-[#eef0ff] via-[#f6f4ff] to-[#e8f6ff]"
    >
      <div aria-hidden="true">
      <div
        className="absolute inset-0 opacity-50"
        style={{ backgroundImage: "radial-gradient(rgb(99 102 241 / 0.18) 1px, transparent 1px)", backgroundSize: "18px 18px" }}
      />

      {CLUTTER.map((c, i) => (
        <div key={c.key} ref={(el) => (clutterRefs.current[i] = el)} className={`scene-clutter absolute z-10 ${c.place}`}>
          <div style={{ transform: `rotate(${c.tilt}deg)` }}>
            <div className={`scene-bob ${i % 2 ? "scene-bob--late" : ""}`}>
              <Clutter kind={c.key} t={t} />
            </div>
          </div>
        </div>
      ))}

      {/* One screen, everything in it done. */}
      <div className="absolute inset-0 z-20 flex items-center justify-center px-4 pb-20">
        <div ref={windowRef} className="scene-window w-full max-w-[21rem] rounded-2xl bg-white p-4 shadow-[0_24px_60px_-20px_rgb(49_46_129/0.45)] ring-1 ring-zinc-900/5">
          <div className="flex items-center gap-2">
            <BrandMark size="sm" />
            <span className="text-sm font-semibold text-zinc-900">{t("home.scene.today")}</span>
            <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/15">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              {t("home.scene.allSet")}
            </span>
          </div>
          <ul className="mt-3 divide-y divide-zinc-100">
            {ROWS.map((row, i) => (
              <li key={row.key} className="scene-row flex items-center gap-2.5 py-2" style={{ "--i": i }}>
                <span className={`scene-tick flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${row.tone}`}>
                  <Tick />
                </span>
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-zinc-800">{t(`home.scene.${row.key}`)}</span>
                <span className="shrink-0 text-[12px] tabular-nums text-zinc-500">{row.value || t(`home.scene.${row.valueKey}`)}</span>
              </li>
            ))}
          </ul>
          <div className="scene-row mt-1 flex items-center justify-between rounded-xl bg-zinc-950 px-3 py-2.5" style={{ "--i": ROWS.length }}>
            <span className="text-[12px] text-zinc-300">{t("home.scene.saved")}</span>
            <span className="text-[15px] font-semibold tabular-nums text-white">
              {t("home.scene.savedValue", { hours: Math.floor(saved / 60), minutes: saved % 60 })}
            </span>
          </div>
        </div>
      </div>
      </div>

      {/* Before and after, named. */}
      <div className="absolute inset-x-3 bottom-3 z-30 flex flex-col items-center gap-1.5">
        <div role="group" aria-label={t("home.scene.toggle")} className="inline-flex rounded-full bg-white/85 p-1 shadow-sm ring-1 ring-zinc-900/10 backdrop-blur">
          {["mess", "sorted"].map((p) => (
            <button
              key={p}
              type="button"
              aria-pressed={phase === p}
              onClick={() => {
                setPicked(true);
                setPhase(p);
              }}
              className={`rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition-colors duration-200 [@media(pointer:coarse)]:min-h-11 ${
                phase === p ? (p === "sorted" ? "bg-indigo-600 text-white" : "bg-zinc-900 text-white") : "text-zinc-600 hover:text-zinc-900"
              }`}
            >
              {t(p === "mess" ? "home.scene.before" : "home.scene.with", { name: APP_NAME })}
            </button>
          ))}
        </div>
        <p className="max-w-[22rem] rounded-full bg-white/70 px-3 py-0.5 text-center text-[12px] leading-snug text-zinc-600 backdrop-blur" aria-live={picked ? "polite" : "off"}>
          {t(phase === "mess" ? "home.scene.beforeNote" : "home.scene.withNote")}
        </p>
      </div>
    </div>
  );
}
