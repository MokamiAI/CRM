import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { APP_NAME } from "../Brand";
import { prefersReducedMotion } from "../../utils/motion";

/*
 * "See yourself in it": six kinds of SMME that quote for a service or a
 * product, each a photo with what YGT did for them today, arriving as
 * notifications. It advances on its own while on screen (paused on hover or focus, and
 * never under reduced motion), and any one can be picked.
 *
 * Photos: Unsplash licence (free for commercial use), see public/home/CREDITS.md.
 * The people pictured are not customers and are given no names or quotes.
 */

export const PEOPLE = [
  { key: "catering", photo: "/home/catering.webp" },
  { key: "construction", photo: "/home/construction.webp" },
  { key: "cleaning", photo: "/home/cleaning.webp" },
  { key: "it", photo: "/home/it.webp" },
  { key: "accounting", photo: "/home/accounting.webp" },
  { key: "events", photo: "/home/events.webp" },
];
const FEED = ["a", "b", "c"];
const TONES = ["bg-indigo-500", "bg-emerald-500", "bg-amber-500"];
const ADVANCE_MS = 5200;

export default function HomePeople() {
  const { t } = useTranslation();
  const rootRef = useRef(null);
  const listRef = useRef(null);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [onScreen, setOnScreen] = useState(false);
  const [reduce] = useState(prefersReducedMotion);
  const running = !reduce && !paused && onScreen;

  useEffect(() => {
    const el = rootRef.current;
    if (!el || !("IntersectionObserver" in window)) return undefined;
    const io = new IntersectionObserver(([entry]) => setOnScreen(entry.isIntersecting), { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!running) return undefined;
    const timer = setTimeout(() => setActive((a) => (a + 1) % PEOPLE.length), ADVANCE_MS);
    return () => clearTimeout(timer);
  }, [active, running]);

  // On phones the picker scrolls sideways: keep the active one in view
  // (moving the row only, never the page).
  useEffect(() => {
    const list = listRef.current;
    const item = list?.children[active];
    if (!item || list.scrollWidth <= list.clientWidth) return;
    list.scrollTo({ left: item.offsetLeft - 20, behavior: reduce ? "auto" : "smooth" });
  }, [active, reduce]);

  const person = PEOPLE[active];

  return (
    <section ref={rootRef} className="py-14" aria-labelledby="home-people">
      <div className="reveal max-w-2xl">
        <h2 id="home-people" className="text-3xl font-semibold tracking-tight text-zinc-900">{t("home.people.title")}</h2>
        <p className="mt-2 text-zinc-600">{t("home.people.intro", { name: APP_NAME })}</p>
      </div>

      <div
        className="reveal mt-8 grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:items-center"
        onPointerEnter={() => setPaused(true)}
        onPointerLeave={() => setPaused(false)}
        onFocus={() => setPaused(true)}
        onBlur={() => setPaused(false)}
      >
        {/* Photo, with their day arriving as notifications. */}
        <div className="relative aspect-[4/5] max-h-[34rem] w-full overflow-hidden rounded-3xl bg-zinc-200 sm:aspect-[5/4] lg:aspect-[4/5]">
          {PEOPLE.map((p, i) => (
            <img
              key={p.key}
              src={p.photo}
              alt={i === active ? t(`home.people.${p.key}.alt`) : ""}
              loading="lazy"
              decoding="async"
              className="people-photo absolute inset-0 h-full w-full object-cover"
              data-active={i === active}
            />
          ))}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-black/60 via-black/20 to-transparent" />
          <div key={person.key} className="absolute inset-x-3 bottom-3 space-y-2 sm:inset-x-auto sm:bottom-5 sm:right-5 sm:w-[19rem]">
            <p className="people-label inline-flex rounded-full bg-white/15 px-3 py-1 text-xs font-medium text-white ring-1 ring-inset ring-white/25 backdrop-blur">
              {t(`home.people.${person.key}.label`)}
            </p>
            {FEED.map((f, i) => (
              <div
                key={f}
                className="people-note flex items-center gap-2.5 rounded-2xl bg-white/90 px-3 py-2.5 shadow-lg ring-1 ring-black/5 backdrop-blur-md"
                style={{ "--i": i }}
              >
                <span className={`h-2 w-2 shrink-0 rounded-full ${TONES[i]}`} aria-hidden="true" />
                <span className="text-[13px] font-medium leading-snug text-zinc-800">{t(`home.people.${person.key}.${f}`)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Pick one. The active one shows how long until the next. */}
        <ul ref={listRef} className="relative flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:gap-1 lg:overflow-visible lg:pb-0">
          {PEOPLE.map((p, i) => {
            const on = i === active;
            return (
              <li key={p.key} className="shrink-0">
                <button
                  type="button"
                  aria-pressed={on}
                  onClick={() => setActive(i)}
                  className={`relative flex w-full items-center gap-3 overflow-hidden rounded-2xl px-3 py-2 text-left transition-colors duration-200 lg:px-4 lg:py-3 ${
                    on ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200/70 lg:bg-transparent lg:hover:bg-zinc-100"
                  }`}
                >
                  <img src={p.photo} alt="" loading="lazy" className="h-8 w-8 shrink-0 rounded-full object-cover lg:h-10 lg:w-10" />
                  <span className="whitespace-nowrap text-sm font-medium lg:whitespace-normal lg:text-[15px]">{t(`home.people.${p.key}.label`)}</span>
                  {on && running && (
                    <span key={active} className="people-progress absolute inset-x-0 bottom-0 h-0.5 bg-white/70" style={{ animationDuration: `${ADVANCE_MS}ms` }} aria-hidden="true" />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
