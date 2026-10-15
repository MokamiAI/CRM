// The two arrival moments: the home page's opening (YGT becomes You Got
// This) and the welcome after signing in. Both are rare by design: the
// intro once per visit, the welcome once per sign-in, so they can afford
// a little ceremony. Either one is skipped by a click or any key.
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import YouGotThis from "./YouGotThis";
import { EASE_OUT, prefersReducedMotion } from "../utils/motion";

const INTRO_KEY = "ygt.intro.seen";
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

/** A full-screen layer that leaves by fading and lifting slightly. */
function useOverlay(onClosed) {
  const layer = useRef(null);
  const leaving = useRef(false);
  const close = useCallback(() => {
    if (leaving.current) return;
    leaving.current = true;
    const el = layer.current;
    if (!el || prefersReducedMotion()) return onClosed();
    el.animate(
      [
        { opacity: 1, transform: "translateY(0)" },
        { opacity: 0, transform: "translateY(-12px)" },
      ],
      { duration: 420, easing: EASE_OUT, fill: "forwards" }
    ).finished.then(onClosed, onClosed);
  }, [onClosed]);
  // Any key or a click skips it; the page underneath doesn't scroll meanwhile.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Tab") return;
      e.preventDefault();
      close();
    };
    window.addEventListener("keydown", onKey);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [close]);
  return { layer, close };
}

/** Home page: once per visit, YGT turns into You Got This, then lifts away. */
export function StartupIntro() {
  const { t } = useTranslation();
  // Not with reduced motion: the point of it is the movement.
  const [show, setShow] = useState(() => !readSession(INTRO_KEY) && !prefersReducedMotion());
  const done = useCallback(() => setShow(false), []);
  useEffect(() => {
    if (show) writeSession(INTRO_KEY, "1");
  }, [show]);
  if (!show) return null;
  return <IntroLayer t={t} onClosed={done} />;
}

function IntroLayer({ t, onClosed }) {
  const { layer, close } = useOverlay(onClosed);
  const finished = useCallback(() => setTimeout(close, 650), [close]);
  return (
    <div
      ref={layer}
      className="fixed inset-0 z-[90] flex cursor-pointer flex-col items-center justify-center bg-white px-6"
      onClick={close}
      role="presentation"
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <span className="aurora-blob -left-24 top-[-4rem] h-96 w-96 bg-violet-300" />
        <span className="aurora-blob right-[-6rem] bottom-[-4rem] h-96 w-96 bg-sky-300" />
      </div>
      <YouGotThis className="relative text-[clamp(2.75rem,11vw,7.5rem)] leading-none" delay={150} onDone={finished} />
      <p className="intro-tagline relative mt-6 text-base font-medium text-slate-600 sm:text-lg">{t("home.hero.title")}</p>
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

/** After signing in: a welcome from the team, once per sign-in. */
export function WelcomeSplash({ name, onClosed }) {
  const { t } = useTranslation();
  const { layer, close } = useOverlay(onClosed);
  const [ready, setReady] = useState(false);
  const go = useRef(null);
  useEffect(() => writeSession(WELCOME_KEY, null), []); // shown: once per sign-in
  const finished = useCallback(() => {
    setReady(true);
    go.current?.focus();
  }, []);
  // It leaves on its own a few seconds after the words land.
  useEffect(() => {
    if (!ready) return undefined;
    const timer = setTimeout(close, 6000);
    return () => clearTimeout(timer);
  }, [ready, close]);
  return (
    <div
      ref={layer}
      className="fixed inset-0 z-[90] flex flex-col items-center justify-center bg-white px-6 text-center"
      onClick={close}
      role="dialog"
      aria-modal="true"
      aria-labelledby="welcome-title"
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <span className="aurora-blob -left-24 top-[-4rem] h-96 w-96 bg-violet-300" />
        <span className="aurora-blob right-[-6rem] bottom-[-4rem] h-96 w-96 bg-sky-300" />
      </div>
      <div className="relative flex max-w-xl flex-col items-center">
        <h1 id="welcome-title" className="welcome-in text-2xl font-semibold tracking-tight text-midnight sm:text-3xl">
          {name ? t("startup.welcomeName", { name }) : t("startup.welcome")}
        </h1>
        <p className="welcome-in mt-2 text-base text-slate-600 [animation-delay:120ms] sm:text-lg">{t("startup.fromTeam")}</p>
        <YouGotThis className="mt-6 text-[clamp(2.5rem,9vw,5.5rem)] leading-none" delay={500} onDone={finished} />
        <p className={`mt-6 text-lg font-medium text-slate-700 transition-[opacity,transform] duration-500 sm:text-xl ${ready ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0"}`}>
          {t("startup.capable")}
        </p>
        <button
          ref={go}
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            close();
          }}
          className={`btn btn-primary mt-8 !h-11 !px-6 transition-opacity duration-500 ${ready ? "opacity-100" : "opacity-0"}`}
        >
          {t("startup.go")}
        </button>
      </div>
    </div>
  );
}
