import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

// Famous lines from salespeople, sales trainers and people who built
// businesses on selling. Kept in their original words. One per week, in order.
export const SALES_QUOTES = [
  { text: "You don't close a sale; you open a relationship if you want to build a long-term, successful enterprise.", by: "Patricia Fripp" },
  { text: "You can have everything in life you want, if you will just help enough other people get what they want.", by: "Zig Ziglar" },
  { text: "Pretend that every single person you meet has a sign around his or her neck that says, 'Make me feel important.'", by: "Mary Kay Ash" },
  { text: "People don't like to be sold, but they love to buy.", by: "Jeffrey Gitomer" },
  { text: "Approach each customer with the idea of helping him or her solve a problem or achieve a goal, not of selling a product or service.", by: "Brian Tracy" },
  { text: "I will persist until I succeed.", by: "Og Mandino" },
  { text: "There is only one boss. The customer.", by: "Sam Walton" },
  { text: "Luck is a dividend of sweat. The more you sweat, the luckier you get.", by: "Ray Kroc" },
  { text: "I never dreamed about success. I worked for it.", by: "Estée Lauder" },
  { text: "Either you run the day or the day runs you.", by: "Jim Rohn" },
  { text: "Every sale has five basic obstacles: no need, no money, no hurry, no desire, no trust.", by: "Zig Ziglar" },
  { text: "Make a customer, not a sale.", by: "Katherine Barchetti" },
  { text: "Treat objections as requests for further information.", by: "Brian Tracy" },
  { text: "Sales are contingent upon the attitude of the salesman, not the attitude of the prospect.", by: "W. Clement Stone" },
  { text: "Aerodynamically, the bumblebee shouldn't be able to fly, but the bumblebee doesn't know it, so it goes on flying anyway.", by: "Mary Kay Ash" },
  { text: "Discipline is the bridge between goals and accomplishment.", by: "Jim Rohn" },
  { text: "Your attitude, not your aptitude, will determine your altitude.", by: "Zig Ziglar" },
  { text: "Success is your duty, obligation and responsibility.", by: "Grant Cardone" },
  { text: "If you work just for money, you'll never make it, but if you love what you're doing and you always put the customer first, success will be yours.", by: "Ray Kroc" },
  { text: "Become the person who would attract the results you seek.", by: "Jim Cathcart" },
  { text: "Always do your best. What you plant now, you will harvest later.", by: "Og Mandino" },
  { text: "Stop selling. Start helping.", by: "Zig Ziglar" },
  { text: "If you are not taking care of your customer, your competitor will.", by: "Bob Hooey" },
  { text: "Formal education will make you a living; self-education will make you a fortune.", by: "Jim Rohn" },
  { text: "High expectations are the key to everything.", by: "Sam Walton" },
  { text: "A goal properly set is halfway reached.", by: "Zig Ziglar" },
  { text: "Ninety percent of selling is conviction and ten percent is persuasion.", by: "Shiv Khera" },
  { text: "The key is not to call the decision maker. The key is to have the decision maker call you.", by: "Jeffrey Gitomer" },
  { text: "Don't find customers for your products, find products for your customers.", by: "Seth Godin" },
  { text: "You don't have to be great to start, but you have to start to be great.", by: "Zig Ziglar" },
];

const HOUR = 3600 * 1000;
const WEEK = 7 * 24 * HOUR;
// A Monday, as the count's starting point.
const ANCHOR = new Date(2024, 0, 1);

/** The week a moment belongs to. Weeks turn over on Monday at 09:00 local
 *  time, so shifting the clock back nine hours makes them start at midnight. */
export function quoteWeek(now = new Date()) {
  const shifted = new Date(now.getTime() - 9 * HOUR);
  const monday = new Date(shifted.getFullYear(), shifted.getMonth(), shifted.getDate() - ((shifted.getDay() + 6) % 7));
  const index = Math.round((monday - ANCHOR) / WEEK);
  return { key: `${monday.getFullYear()}-${monday.getMonth() + 1}-${monday.getDate()}`, quote: SALES_QUOTES[((index % SALES_QUOTES.length) + SALES_QUOTES.length) % SALES_QUOTES.length] };
}

const STORE = "ygt.quoteSeen.";
function seen(who) {
  try {
    return localStorage.getItem(STORE + who);
  } catch {
    return null;
  }
}
function markSeen(who, key) {
  try {
    localStorage.setItem(STORE + who, key);
  } catch {
    /* private mode: it may show again, which is harmless */
  }
}

/** The sales quote of the week: a card pinned to the bottom of the screen,
 *  shown once per person per week from Monday 09:00. `who` is the user's id,
 *  or "guest" on the sign-in and sign-up screens. `hold` delays it (e.g. while
 *  the welcome tour is running). */
export default function QuoteOfTheWeek({ who = "guest", hold = false, className = "" }) {
  const { t } = useTranslation();
  const [week, setWeek] = useState(() => quoteWeek());
  const [state, setState] = useState("hidden"); // hidden | open | closing

  // Notice Monday 09:00 arriving while the app is already open.
  useEffect(() => {
    const timer = setInterval(() => setWeek((w) => (quoteWeek().key === w.key ? w : quoteWeek())), 60 * 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (hold || state !== "hidden") return undefined;
    // Seen on this device before signing in counts for the person too.
    if (who !== "guest" && seen("guest") === week.key) markSeen(who, week.key);
    if (seen(who) === week.key) return undefined;
    const timer = setTimeout(() => setState("open"), 900);
    return () => clearTimeout(timer);
  }, [who, hold, week.key]); // eslint-disable-line react-hooks/exhaustive-deps

  const close = useCallback(() => {
    markSeen(who, week.key);
    setState("closing");
    setTimeout(() => setState("hidden"), 200);
  }, [who, week.key]);

  useEffect(() => {
    if (state !== "open") return undefined;
    const onKey = (e) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state, close]);

  if (state === "hidden") return null;
  return (
    <aside
      role="status"
      aria-labelledby="quote-week-title"
      className={`quote-week ${state === "closing" ? "quote-week-out" : ""} fixed inset-x-4 z-[60] mx-auto max-w-md overflow-hidden rounded-2xl bg-zinc-900 text-white shadow-pop ${className}`}
    >
      <span className="brand-bg absolute inset-x-0 top-0 h-1" aria-hidden="true" />
      <div className="p-5 pt-6">
        <div className="flex items-center gap-2">
          <span className="text-lg leading-none" aria-hidden="true">🔥</span>
          <h2 id="quote-week-title" className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300">
            {t("quoteWeek.title")}
          </h2>
          <button
            type="button"
            onClick={close}
            className="ml-auto -mr-2 -mt-1 flex h-8 w-8 items-center justify-center rounded-full text-zinc-400 transition-colors duration-150 hover:bg-white/10 hover:text-white"
            aria-label={t("common.close")}
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-4 w-4" aria-hidden="true">
              <path d="m4 4 8 8M12 4l-8 8" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <blockquote className="mt-3 text-[17px] font-medium leading-snug tracking-tight">“{week.quote.text}”</blockquote>
        <p className="mt-2 text-sm text-zinc-400">— {week.quote.by}</p>
        <div className="mt-4 flex items-center justify-between gap-3">
          <span className="text-xs text-zinc-500">{t("quoteWeek.footer")}</span>
          <button type="button" onClick={close} className="btn brand-bg !h-9 shrink-0 !px-4 !text-sm text-white">
            {t("quoteWeek.go")}
          </button>
        </div>
      </div>
    </aside>
  );
}
