// The two arrival moments: the home page's opening (YGT becomes You Got
// This) and the welcome after signing in. Both are rare by design: the
// intro once per visit, the welcome once per sign-in, so they can afford
// a little ceremony. Either one is skipped by a click or any key.
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import YouGotThis from "./YouGotThis";
import { EASE_OUT, prefersReducedMotion } from "../utils/motion";

const INTRO_KEY = "ygt.intro.seen";
// On <html> while the intro shows: the home page holds its entrance.
export const INTRO_CLASS = "ygt-intro";
export const INTRO_DONE = "ygt:intro-done";

/** The intro is leaving: let the home page make its entrance. */
function releasePage() {
  if (!document.documentElement.classList.contains(INTRO_CLASS)) return;
  document.documentElement.classList.remove(INTRO_CLASS);
  window.dispatchEvent(new Event(INTRO_DONE));
}
const WELCOME_KEY = "ygt.welcome";

function readSession(key) {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}
function writeSession(key, value) {
  try {
    if (value == null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch {
    /* private mode: the moment may repeat or be skipped, which is harmless */
  }
}

/** Call after a successful sign-in: the app greets the person once. */
export function queueWelcome() {
  writeSession(WELCOME_KEY, "1");
}

/** Is a welcome waiting? (WelcomeSplash clears it once shown.) */
export function welcomeQueued() {
  return readSession(WELCOME_KEY) === "1";
}

/** A full-screen layer. It can close gracefully (the words play backwards,
 *  then the layer fades and lifts) or at once; a second request while the
 *  graceful close is playing skips the rest of it. */
function useOverlay(onClosed, outro, { keysGraceful = false, onLeaving, tabSkips = false } = {}) {
  const layer = useRef(null);
  const phase = useRef("open"); // open | outro | leaving
  const [closing, setClosing] = useState(false);
  const leave = useCallback(() => {
    if (phase.current === "leaving") return;
    phase.current = "leaving";
    onLeaving?.();
    const el = layer.current;
    if (!el || prefersReducedMotion()) return onClosed();
    el.animate(
      [
        { opacity: 1, transform: "translateY(0)" },
        { opacity: 0, transform: "translateY(-12px)" },
      ],
      { duration: 420, easing: EASE_OUT, fill: "forwards" }
    ).finished.then(onClosed, onClosed);
  }, [onClosed, onLeaving]);
  const close = useCallback(
    (graceful = false) => {
      if (phase.current === "open" && graceful && outro) {
        phase.current = "outro";
        setClosing(true);
        outro().then(leave);
      } else {
        leave();
      }
    },
    [outro, leave]
  );
  // Any key closes it (gracefully where asked); the page doesn't scroll meanwhile.
  // Tab stays inside a dialog, but skips an overlay that has nothing to focus.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Tab" && !tabSkips) return;
      e.preventDefault();
      close(keysGraceful);
    };
    window.addEventListener("keydown", onKey);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [close, keysGraceful, tabSkips]);
  return { layer, close, closing };
}

/** Home page: once per visit, YGT turns into You Got This, holds, then
 *  folds back into YGT and lifts away. */
export function StartupIntro() {
  const { t } = useTranslation();
  // Not with reduced motion: the point of it is the movement.
  const [show, setShow] = useState(() => {
    const first = !readSession(INTRO_KEY) && !prefersReducedMotion();
    if (first) document.documentElement.classList.add(INTRO_CLASS); // before the page paints
    return first;
  });
  const done = useCallback(() => setShow(false), []);
  useEffect(() => {
    if (show) writeSession(INTRO_KEY, "1");
  }, [show]);
  if (!show) return null;
  return <IntroLayer t={t} onClosed={done} />;
}

const INTRO_HOLD = 1500; // ms "You Got This" stays before folding back

function IntroLayer({ t, onClosed }) {
  const words = useRef(null);
  const outro = useCallback(() => words.current?.outro() ?? Promise.resolve(), []);
  // While it shows, the page behind can't be reached by keyboard or screen
  // reader; it comes back the moment the intro starts to leave.
  const hidden = useRef([]);
  const reveal = useCallback(() => {
    hidden.current.forEach((el) => (el.inert = false));
    hidden.current = [];
    releasePage();
  }, []);
  const { layer, close, closing } = useOverlay(onClosed, outro, { onLeaving: reveal, tabSkips: true });
  useEffect(() => {
    const siblings = [...(layer.current?.parentElement?.children ?? [])].filter((el) => el !== layer.current && !el.inert);
    siblings.forEach((el) => (el.inert = true));
    hidden.current = siblings;
    return reveal; // also if it goes away some other way
  }, [layer, reveal]);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  const finished = useCallback(() => {
    timer.current = setTimeout(() => close(true), INTRO_HOLD);
  }, [close]);
  return (
    <div
      ref={layer}
      className="fixed inset-0 z-[90] flex cursor-pointer flex-col items-center justify-center bg-white px-6"
      onClick={() => close()}
      role="presentation"
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <span className="aurora-blob -left-24 top-[-4rem] h-96 w-96 bg-violet-300" />
        <span className="aurora-blob right-[-6rem] bottom-[-4rem] h-96 w-96 bg-sky-300" />
      </div>
      <YouGotThis ref={words} className="relative text-[clamp(2.75rem,11vw,7.5rem)] leading-none" delay={150} onDone={finished} />
      <div className={`relative transition-opacity duration-300 ${closing ? "opacity-0" : "opacity-100"}`}>
        <p className="intro-tagline mt-6 text-base font-medium text-slate-600 sm:text-lg">{t("home.hero.title")}</p>
      </div>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          close();
        }}
        className="absolute bottom-6 right-6 rounded-full px-4 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-800"
      >
        {t("startup.skip")}
      </button>
    </div>
  );
}

const WELCOME_HOLD = 3500; // ms after the words land before it closes itself

/** After signing in: a welcome from the team, once per sign-in. Closing
 *  (button, key, click or on its own) folds the words back into YGT. */
export function WelcomeSplash({ name, returning = false, onClosed }) {
  // Someone who has been here before: a short hello, not the whole welcome.
  if (returning) return <WelcomeBack name={name} onClosed={onClosed} />;
  return <FirstWelcome name={name} onClosed={onClosed} />;
}

const BACK_HOLD = 1300; // ms the returning user's greeting stays before fading

/** "Welcome back, Thandi": the YGT letters rise in, then it fades
 *  away, about two seconds in all. Any key or click closes it sooner. */
function WelcomeBack({ name, onClosed }) {
  const { t } = useTranslation();
  const { layer, close } = useOverlay(onClosed);
  useEffect(() => writeSession(WELCOME_KEY, null), []); // shown: once per sign-in
  useEffect(() => {
    const timer = setTimeout(() => close(), BACK_HOLD);
    return () => clearTimeout(timer);
  }, [close]);
  return (
    <div
      ref={layer}
      className="fixed inset-0 z-[90] flex flex-col items-center justify-center bg-white px-6 text-center"
      onClick={() => close()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="welcome-title"
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <span className="aurora-blob -left-24 top-[-4rem] h-96 w-96 bg-violet-300" />
        <span className="aurora-blob right-[-6rem] bottom-[-4rem] h-96 w-96 bg-sky-300" />
      </div>
      <span className="brand-join relative inline-flex text-[clamp(3.5rem,12vw,6.5rem)] font-extrabold leading-none tracking-[-0.04em]" aria-hidden="true">
        <span className="brand-text">Y</span>
        <span className="brand-text">G</span>
        <span className="brand-text">T</span>
      </span>
      <h1 id="welcome-title" className="welcome-in relative mt-5 text-2xl font-semibold tracking-tight text-midnight [animation-delay:200ms] sm:text-3xl">
        {name ? t("startup.welcomeBackName", { name }) : t("startup.welcomeBack")}
      </h1>
    </div>
  );
}

function FirstWelcome({ name, onClosed }) {
  const { t } = useTranslation();
  const words = useRef(null);
  const outro = useCallback(() => words.current?.outro() ?? Promise.resolve(), []);
  const { layer, close, closing } = useOverlay(onClosed, outro, { keysGraceful: true });
  const [ready, setReady] = useState(false);
  const go = useRef(null);
  useEffect(() => writeSession(WELCOME_KEY, null), []); // shown: once per sign-in
  const finished = useCallback(() => {
    setReady(true);
    go.current?.focus();
  }, []);
  // It closes on its own a while after the words land.
  useEffect(() => {
    if (!ready) return undefined;
    const timer = setTimeout(() => close(true), WELCOME_HOLD);
    return () => clearTimeout(timer);
  }, [ready, close]);
  const shown = ready && !closing;
  return (
    <div
      ref={layer}
      className="fixed inset-0 z-[90] flex flex-col items-center justify-center bg-white px-6 text-center"
      onClick={() => close(true)}
      role="dialog"
      aria-modal="true"
      aria-labelledby="welcome-title"
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <span className="aurora-blob -left-24 top-[-4rem] h-96 w-96 bg-violet-300" />
        <span className="aurora-blob right-[-6rem] bottom-[-4rem] h-96 w-96 bg-sky-300" />
      </div>
      <div className="relative flex max-w-xl flex-col items-center">
        <div className={`transition-opacity duration-300 ${closing ? "opacity-0" : "opacity-100"}`}>
          <h1 id="welcome-title" className="welcome-in text-2xl font-semibold tracking-tight text-midnight sm:text-3xl">
            {name ? t("startup.welcomeName", { name }) : t("startup.welcome")}
          </h1>
          <p className="welcome-in mt-2 text-base text-slate-600 [animation-delay:120ms] sm:text-lg">{t("startup.fromTeam")}</p>
        </div>
        <YouGotThis ref={words} className="mt-6 text-[clamp(2.5rem,9vw,5.5rem)] leading-none" delay={500} onDone={finished} />
        <p className={`mt-6 text-lg font-medium text-slate-700 transition-[opacity,transform] duration-500 sm:text-xl ${shown ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0"}`}>
          {t("startup.capable")}
        </p>
        <button
          ref={go}
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            close(true);
          }}
          className={`btn btn-primary mt-8 !h-11 !px-6 transition-opacity duration-500 ${shown ? "opacity-100" : "opacity-0"}`}
        >
          {t("startup.go")}
        </button>
      </div>
    </div>
  );
}
