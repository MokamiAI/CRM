import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { APP_NAME, BrandMark } from "./Brand";

/*
 * First-run guided tour. A dimmed backdrop with a spotlight on one part of
 * the app at a time, and a box explaining what it is and what's on it.
 *
 * Steps point at elements by their data-tour attribute. A step whose
 * element isn't on screen (e.g. the sidebar on a phone) still shows, as a
 * centered box, so the tour reads the same everywhere.
 */
const STEPS = [
  { key: "welcome" },
  { key: "dashboard", target: "dash-kpis" },
  { key: "charts", target: "dash-charts" },
  { key: "day", target: "dash-day" },
  { key: "getStarted", target: "get-started" },
  { key: "activities", target: "activities" },
  { key: "messages", target: "messages" },
  { key: "deals", target: "deals" },
  { key: "quotes", target: "quotes" },
  { key: "invoices", target: "invoices" },
  { key: "marketing", target: "marketing" },
  { key: "customers", target: "customers" },
  { key: "products", target: "products" },
  { key: "search", target: "search" },
  { key: "settings", target: "settings", admin: true },
  { key: "language", target: "language" },
  { key: "about", target: "about" },
  { key: "help", target: "help" },
  { key: "done" },
];
// Steps with "what's on it" bullets (help.sections.<key>.p1..p4).
const PARTS = ["p1", "p2", "p3", "p4"];
const PAD = 6;
const BOX_WIDTH = 340;

const TourContext = createContext({ start: () => {} });
export const useTour = () => useContext(TourContext);

function visibleTarget(name) {
  if (!name) return null;
  return [...document.querySelectorAll(`[data-tour="${name}"]`)].find((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  });
}

function measure(el) {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 };
}

/** Where the box goes: beside a narrow target on the left (the sidebar),
 *  otherwise below it, or above when there's no room below. */
function placeBox(rect, height) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (!rect || vw < 640) return null; // centered (phones, or nothing to point at)
  const width = Math.min(BOX_WIDTH, vw - 32);
  const clampTop = (top) => Math.max(16, Math.min(top, vh - height - 16));
  if (rect.left + rect.width < 320 && rect.left + rect.width + 16 + width < vw) {
    return { left: rect.left + rect.width + 16, top: clampTop(rect.top), width, origin: "left center" };
  }
  const left = Math.max(16, Math.min(rect.left, vw - width - 16));
  const below = vh - (rect.top + rect.height + 12) - 16;
  const above = rect.top - 12 - 16;
  if (below >= height || below >= above) return { left, top: clampTop(rect.top + rect.height + 12), width, origin: "top left" };
  return { left, top: clampTop(rect.top - 12 - height), width, origin: "bottom left" };
}

export function TourProvider({ children }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { user, markTourDone } = useAuth();
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState(null);
  const nextButton = useRef(null);
  const boxRef = useRef(null);
  const [boxHeight, setBoxHeight] = useState(320);

  const isAdmin = user?.role === "admin";
  const steps = STEPS.filter((s) => !s.admin || isAdmin);
  const step = steps[index];

  const start = useCallback(() => {
    navigate("/");
    setIndex(0);
    setOpen(true);
  }, [navigate]);

  const finish = useCallback(() => {
    setOpen(false);
    markTourDone(true);
  }, [markTourDone]);

  // First sign-in: start once the dashboard has had a moment to render.
  useEffect(() => {
    if (!user || user.tour_completed_at) return undefined;
    const timer = setTimeout(start, 700);
    return () => clearTimeout(timer);
  }, [user?.id, user?.tour_completed_at]); // eslint-disable-line react-hooks/exhaustive-deps

  // Find, scroll to and measure the current step's element; keep it in
  // place on resize/scroll. Steps whose element is missing are centered.
  useLayoutEffect(() => {
    if (!open) return undefined;
    let el = visibleTarget(step?.target);
    // An optional step (e.g. Get started, once dismissed) is skipped entirely.
    if (step?.target === "get-started" && !el) {
      setIndex((i) => i + 1);
      return undefined;
    }
    el?.scrollIntoView({ block: "nearest" });
    const update = () => {
      el = visibleTarget(step?.target);
      setRect(measure(el));
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open, index, step?.target]);

  useEffect(() => {
    if (!open) return undefined;
    nextButton.current?.focus({ preventScroll: true });
    const onKey = (e) => {
      if (e.key === "Escape") finish();
      else if (e.key === "ArrowRight") setIndex((i) => Math.min(i + 1, steps.length - 1));
      else if (e.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, index, steps.length, finish]);

  // The box's real height (it varies by step), so it never covers its target.
  useLayoutEffect(() => {
    if (open && boxRef.current) setBoxHeight(boxRef.current.offsetHeight);
  });

  const last = index === steps.length - 1;
  const box = placeBox(rect, boxHeight);
  const name = (user?.full_name || "").split(" ")[0];
  const section = `help.sections.${step?.key}`;
  const parts = PARTS.filter((p) => i18n.exists(`${section}.${p}`)).map((p) => t(`${section}.${p}`));

  return (
    // busy: the tour is showing, or is about to on a first sign-in.
    <TourContext.Provider value={{ start, busy: open || (!!user && !user.tour_completed_at) }}>
      {children}
      {open && step && (
        <div className="fixed inset-0 z-[70]" role="dialog" aria-modal="true" aria-labelledby="tour-title">
          {/* The spotlight: a cut-out made by one huge shadow, moved between
              steps with an on-screen ease-in-out. No target: plain dimming. */}
          {rect ? (
            <div
              className="tour-spotlight pointer-events-none fixed rounded-xl"
              style={{ transform: `translate(${rect.left}px, ${rect.top}px)`, width: rect.width, height: rect.height }}
            />
          ) : (
            <div className="tour-dim fixed inset-0" />
          )}

          <div
            key={step.key}
            ref={boxRef}
            className={`tour-box fixed rounded-2xl bg-white p-5 shadow-pop ring-1 ring-zinc-200/80 ${box ? "" : "tour-box-center"}`}
            style={box ? { left: box.left, top: box.top, width: box.width, transformOrigin: box.origin } : undefined}
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">
                {t("tour.stepOf", { step: index + 1, total: steps.length })}
              </span>
              <button type="button" onClick={finish} className="text-xs font-medium text-zinc-400 hover:text-zinc-700">
                {t("tour.skip")}
              </button>
            </div>

            {(step.key === "welcome" || step.key === "done") && <BrandMark size="md" join className="mb-3" />}
            <h2 id="tour-title" className="text-lg font-semibold text-zinc-900">
              {t(`tour.${step.key}Title`, { defaultValue: t(`${section}.title`), name: name || "", app: APP_NAME })}
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-zinc-600">
              {t(`tour.${step.key}Body`, { defaultValue: t(`${section}.summary`), app: APP_NAME })}
            </p>
            {parts.length > 0 && (
              <div className="mt-3 rounded-lg bg-zinc-50 p-3 ring-1 ring-inset ring-zinc-200/70">
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{t("tour.whatsHere")}</p>
                <ul className="space-y-1 text-[13px] text-zinc-700">
                  {parts.map((part) => (
                    <li key={part} className="flex gap-2">
                      <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-indigo-500" aria-hidden="true" />
                      {part}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-4 flex items-center justify-between gap-3">
              <div className="h-1 min-w-0 max-w-24 flex-1 overflow-hidden rounded-full bg-zinc-200" aria-hidden="true">
                <div
                  className="h-full w-full origin-left rounded-full bg-indigo-600 transition-transform duration-300 ease-out"
                  style={{ transform: `scaleX(${(index + 1) / steps.length})` }}
                />
              </div>
              <div className="flex shrink-0 gap-2">
                {index > 0 && (
                  <button type="button" className="btn btn-secondary !h-9 !text-sm" onClick={() => setIndex(index - 1)}>
                    {t("tour.back")}
                  </button>
                )}
                {last ? (
                  <>
                    <button
                      type="button"
                      className="btn btn-secondary !h-9 !text-sm"
                      onClick={() => {
                        finish();
                        navigate("/help");
                      }}
                    >
                      {t("tour.openHelp")}
                    </button>
                    <button ref={nextButton} type="button" className="btn btn-primary !h-9 !text-sm" onClick={finish}>
                      {t("tour.finish")}
                    </button>
                  </>
                ) : (
                  <button ref={nextButton} type="button" className="btn btn-primary !h-9 !text-sm" onClick={() => setIndex(index + 1)}>
                    {index === 0 ? t("tour.start") : t("tour.next")}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </TourContext.Provider>
  );
}
