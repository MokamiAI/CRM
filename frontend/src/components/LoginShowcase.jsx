import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { prefersReducedMotion } from "../utils/motion";

/*
 * The sign-in screen's right panel: a small live demo of what the product
 * does (send → remind → paid), with depth that follows the pointer.
 *
 * Motion budget: this is the once-a-day screen, the marketing/explanatory
 * tier, so longer beats and decorative pointer-tracking are allowed here
 * (and nowhere in the app itself). Everything moves via transform/opacity
 * set directly on each element, never through a CSS variable on a parent.
 */

const STEPS = [
  { key: "sent", tone: "sky", when: "4 Oct" },
  { key: "reminded", tone: "amber", when: "1 Nov" },
  { key: "paid", tone: "emerald", when: "2 Nov" },
];
const STEP_MS = 2400;
const AMOUNT = 14605;

const TONES = {
  sky: "bg-sky-400/10 text-sky-300 ring-sky-400/25",
  amber: "bg-amber-400/10 text-amber-300 ring-amber-400/25",
  emerald: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/25",
};
const DOTS = { sky: "bg-sky-400", amber: "bg-amber-400", emerald: "bg-emerald-400" };

const money = (n) => `R ${Math.round(n).toLocaleString("en-ZA").replace(/,/g, " ")},00`;

// Smoothly follows the pointer: each frame moves a fraction of the way to
// the target (exponential smoothing, a cheap spring without overshoot),
// so the depth effect has weight instead of snapping to the mouse.
function usePointerDepth(panelRef, layers) {
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel || prefersReducedMotion() || !window.matchMedia("(pointer: fine)").matches) return;
    const target = { x: 0, y: 0, px: -999, py: -999 };
    const current = { x: 0, y: 0, px: -999, py: -999 };
    let frame = null;

    const tick = () => {
      let moving = false;
      for (const k of ["x", "y", "px", "py"]) {
        const delta = target[k] - current[k];
        current[k] += delta * 0.12;
        if (Math.abs(delta) > 0.001) moving = true;
      }
      for (const { ref, depth, tilt } of layers) {
        const el = ref.current;
        if (!el) continue;
        const tx = current.x * depth;
        const ty = current.y * depth;
        el.style.transform = tilt
          ? `perspective(900px) translate3d(${tx}px, ${ty}px, 0) rotateX(${-current.y * tilt}deg) rotateY(${current.x * tilt}deg)`
          : `translate3d(${tx}px, ${ty}px, 0)`;
      }
      const spot = panel.querySelector("[data-spotlight]");
      if (spot) spot.style.transform = `translate3d(${current.px - 300}px, ${current.py - 300}px, 0)`;
      frame = moving ? requestAnimationFrame(tick) : null;
    };
    const kick = () => {
      if (!frame) frame = requestAnimationFrame(tick);
    };
    const onMove = (event) => {
      const rect = panel.getBoundingClientRect();
      // -1..1 from the panel centre
      target.x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      target.y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
      target.px = event.clientX - rect.left;
      target.py = event.clientY - rect.top;
      kick();
    };
    const onLeave = () => {
      target.x = 0;
      target.y = 0;
      kick();
    };
    panel.addEventListener("pointermove", onMove);
    panel.addEventListener("pointerleave", onLeave);
    return () => {
      panel.removeEventListener("pointermove", onMove);
      panel.removeEventListener("pointerleave", onLeave);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [panelRef, layers]);
}

export default function LoginShowcase() {
  const { t } = useTranslation();
  const panelRef = useRef(null);
  const cardRef = useRef(null);
  const backRef = useRef(null);
  const frontRef = useRef(null);
  const [layers] = useState(() => [
    { ref: cardRef, depth: 10, tilt: 5 },
    { ref: backRef, depth: -18 },
    { ref: frontRef, depth: 26 },
  ]);
  usePointerDepth(panelRef, layers);

  // The story loop: sent → reminded → paid, then start again.
  const [step, setStep] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStep((s) => (s + 1) % STEPS.length), STEP_MS);
    return () => clearInterval(t);
  }, []);
  const current = STEPS[step];
  const paid = current.key === "paid";

  // Amount "collected" counts up when the payment lands (explanatory
  // motion: it's showing the money arriving, not decorating a figure
  // someone is trying to read).
  const [collected, setCollected] = useState(0);
  useEffect(() => {
    if (!paid) {
      setCollected(0);
      return;
    }
    if (prefersReducedMotion()) {
      setCollected(AMOUNT);
      return;
    }
    const start = performance.now();
    let raf;
    const run = (now) => {
      const t = Math.min((now - start) / 700, 1);
      setCollected(AMOUNT * (1 - Math.pow(1 - t, 3))); // ease-out cubic
      if (t < 1) raf = requestAnimationFrame(run);
    };
    raf = requestAnimationFrame(run);
    return () => cancelAnimationFrame(raf);
  }, [paid]);

  return (
    <div ref={panelRef} className="relative flex h-full w-full items-center justify-center overflow-hidden bg-zinc-950">
      {/* Grid, revealed brighter under a spotlight that trails the pointer. */}
      <div
        className="absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage: "linear-gradient(to right, white 1px, transparent 1px), linear-gradient(to bottom, white 1px, transparent 1px)",
          backgroundSize: "32px 32px",
          maskImage: "radial-gradient(ellipse at center, black 35%, transparent 80%)",
        }}
        aria-hidden="true"
      />
      <div
        data-spotlight
        className="pointer-events-none absolute left-0 top-0 h-[600px] w-[600px] rounded-full opacity-60"
        style={{ background: "radial-gradient(circle, rgb(139 92 246 / 0.22), transparent 60%)", transform: "translate3d(-999px,-999px,0)" }}
        aria-hidden="true"
      />
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <span className="aurora-blob -right-24 -top-24 h-96 w-96 bg-violet-600 !opacity-30" />
        <span className="aurora-blob -bottom-32 -left-16 h-96 w-96 bg-sky-500 !opacity-20" />
      </div>

      <div className="relative w-full max-w-sm px-8" aria-hidden="true">
        {/* The card and its two satellites share one box, so the chips
            anchor to the card's corners rather than to the whole panel. */}
        <div className="relative">
        {/* Back card: drifts opposite the pointer, sits behind. */}
        <div ref={backRef} className="absolute -right-2 -top-14 z-0 will-change-transform">
          <div className="showcase-float rounded-xl bg-white/[0.05] px-3.5 py-2.5 ring-1 ring-white/10 backdrop-blur">
            <p className="text-[11px] text-zinc-400">{t("showcase.dealWon")}</p>
            <p className="text-sm font-semibold text-white">+ R 48 000,00</p>
          </div>
        </div>

        {/* Main invoice card: tilts toward the pointer. */}
        <div ref={cardRef} className="relative z-10 will-change-transform">
          <div className="relative overflow-hidden rounded-2xl bg-white/[0.05] p-5 shadow-2xl ring-1 ring-white/10 backdrop-blur-md">
            {paid && <span key={step} className="showcase-shine" />}
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-white">INV-0042</span>
              <span key={current.key} className={`showcase-swap inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[current.tone]}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${DOTS[current.tone]}`} />
                {t(`showcase.badge.${current.key}`)}
              </span>
            </div>
            <p className="mt-4 text-3xl font-semibold tracking-tight text-white">R 14 605,00</p>
            <p className="mt-1 h-5 text-sm text-zinc-400">
              {paid ? (
                <span className="text-emerald-300">{t("showcase.collected", { amount: money(collected) })}</span>
              ) : current.key === "reminded" ? (
                t("showcase.reminding")
              ) : (
                t("showcase.due")
              )}
            </p>

            {/* Timeline: a rail with a dot that travels to the current step. */}
            <div className="relative mt-5 border-t border-white/10 pt-4">
              <span className="absolute bottom-[9px] left-[5px] top-[25px] w-px bg-white/10" />
              <span
                className="absolute left-[2px] top-[22px] h-[7px] w-[7px] rounded-full bg-white shadow-[0_0_12px_2px_rgb(255_255_255/0.5)] transition-transform duration-500 ease-in-out"
                style={{ transform: `translateY(${step * 28}px)` }}
              />
              <ul className="space-y-[10px] text-sm">
                {STEPS.map((s, i) => (
                  <li
                    key={s.key}
                    className={`flex h-[18px] items-center justify-between pl-5 transition-colors duration-300 ${
                      i < step ? "text-zinc-400" : i === step ? "text-white" : "text-zinc-600"
                    }`}
                  >
                    <span>{t(`showcase.line.${s.key}`)}</span>
                    <span>{s.when}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        {/* Front chip: drifts with the pointer, closest to the viewer. */}
        <div ref={frontRef} className="absolute -bottom-10 -left-6 z-20 will-change-transform">
          <div className="showcase-float showcase-float--late flex items-center gap-2 rounded-xl bg-white px-3 py-2 shadow-pop">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
              <svg viewBox="0 0 16 16" fill="none" className="h-3.5 w-3.5">
                <path d="M3.5 8.5 6.5 11.5 12.5 4.5" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <span className="text-xs font-medium text-zinc-800">{t("showcase.remindersToday")}</span>
          </div>
        </div>

        </div>

        <div className="relative mt-16">
          <p className="text-xl font-semibold leading-snug text-white">
            {t("showcase.headline")} <span className="showcase-gradient-text">{t("showcase.headlineAccent")}</span>
          </p>
          <p className="mt-2 text-sm text-zinc-400">
            {t("showcase.subline")}
          </p>
        </div>
      </div>
    </div>
  );
}
