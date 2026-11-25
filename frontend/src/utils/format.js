import i18n from "../i18n";
import { intlLocale } from "../i18n/languages";

// YGT's own prices (plans, seats, subscription invoices) are always in rand,
// wherever the company is.
export const YGT_CURRENCY = "ZAR";

// The company's country and currency (from /company, see AppLayout),
// remembered so the first paint after a reload is already right.
const REGION_KEY = "ygt.region";
const fallbackRegion = { currency: import.meta.env.VITE_CURRENCY || "ZAR", country: "ZA" };
let region = (() => {
  try {
    const saved = JSON.parse(localStorage.getItem(REGION_KEY) || "null");
    if (saved?.currency && saved?.country) return saved;
  } catch {
    /* private mode: the default until the company loads */
  }
  return fallbackRegion;
})();

export const getRegion = () => region;

/** The company's currency code, e.g. "KES" (for labels like "Value (KES)"). */
export const currencyCode = () => region.currency;

/** Called with the company profile; true (and the app re-renders) if the
 *  currency or country changed. */
export function setRegion(company) {
  const next = { currency: (company?.default_currency || "ZAR").toUpperCase(), country: (company?.country || "ZA").toUpperCase() };
  if (next.currency === region.currency && next.country === region.country) return false;
  region = next;
  try {
    localStorage.setItem(REGION_KEY, JSON.stringify(next));
  } catch {
    /* not remembered; set again next load */
  }
  i18n.emit("regionChanged", `${next.country}-${next.currency}`);
  return true;
}

// Numbers and dates follow the UI language. English outside South Africa
// uses that country's English conventions ("KES 1,500.00" in Kenya, not
// South Africa's "1 500,00"); a company elsewhere ("ZZ") uses the browser's.
const countryLocales = new Map();
function locale() {
  const language = i18n.language;
  if (language !== "en" || region.country === "ZA") return intlLocale(language);
  const key = region.country;
  if (!countryLocales.has(key)) {
    const browser = typeof navigator !== "undefined" && navigator.language?.startsWith("en") ? navigator.language : "en-GB";
    const tag = key === "ZZ" ? browser : `en-${key}`;
    const ok = Intl.NumberFormat.supportedLocalesOf([tag]).length > 0;
    countryLocales.set(key, ok ? tag : "en-GB");
  }
  return countryLocales.get(key);
}

// Intl formatters are costly to build, so one is cached per locale + options.
const cache = new Map();
function formatter(Kind, options) {
  const tag = locale();
  const key = `${Kind.name}|${tag}|${JSON.stringify(options)}`;
  if (!cache.has(key)) cache.set(key, new Kind(tag, options));
  return cache.get(key);
}

// API amounts are Decimal strings ("1500.00"); never do maths on them as
// floats beyond display and simple sums. Always to the cent, whatever the
// currency, so what's shown matches what's stored and owed.
export function formatMoney(value, currency = region.currency) {
  const amount = Number(value ?? 0);
  return formatter(Intl.NumberFormat, { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
    Number.isFinite(amount) ? amount : 0
  );
}

/** YGT's own amounts (subscription invoices, refunds): always rand. */
export const formatRand = (value) => formatMoney(value, YGT_CURRENCY);

// Whole amounts in tiles: "R 149", "R 1 490" (no cents).
export function formatMoneyWhole(value, currency = region.currency) {
  return formatter(Intl.NumberFormat, { style: "currency", currency, minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(Number(value ?? 0));
}

/** YGT's plan prices: always rand ("R 199"), wherever the company is. */
export const formatRandWhole = (value) => formatMoneyWhole(value, YGT_CURRENCY);

// Axis ticks and tight spaces: "R 185k", "R 1,2M".
export function formatMoneyCompact(value) {
  return formatter(Intl.NumberFormat, { style: "currency", currency: region.currency, notation: "compact", minimumFractionDigits: 0, maximumFractionDigits: 1 }).format(
    Number(value ?? 0)
  );
}

// Tiles and small boxes: exact up to a million ("R 465 060"), then short
// ("R 125M", "R 4,5M"), so big pipelines never spill out of their box.
// Show the exact amount as a tooltip (title) next to it.
export function formatMoneyFit(value, limit = 1_000_000) {
  return Math.abs(Number(value ?? 0)) >= limit ? formatMoneyCompact(value) : formatMoneyWhole(value);
}

// "2026-10-05" is a calendar date with no timezone. new Date("2026-10-05")
// would parse it as UTC midnight and can show the previous day west of
// UTC, so build it from its parts in local time.
function localDate(value) {
  const [y, m, d] = String(value).slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function formatDate(value) {
  if (!value) return "—";
  return formatter(Intl.DateTimeFormat, { day: "numeric", month: "short", year: "numeric" }).format(localDate(value));
}

// For dense list rows on a phone: "4 Nov", with the year only when it
// isn't this year.
export function formatShortDate(value) {
  if (!value) return "—";
  const date = localDate(value);
  return date.getFullYear() === new Date().getFullYear()
    ? formatter(Intl.DateTimeFormat, { day: "numeric", month: "short" }).format(date)
    : formatDate(value);
}

export function formatDateTime(iso, options) {
  return formatter(Intl.DateTimeFormat, options).format(new Date(iso));
}

export function formatMonth(iso, style = "short") {
  const [y, m] = String(iso).split("-").map(Number);
  return formatter(Intl.DateTimeFormat, { month: style, ...(style === "long" && { year: "numeric" }) }).format(new Date(y, m - 1, 1));
}

export function todayISO() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * A user-facing message for a failed request. The API's messages are in
 * English, so a translation for its stable `error_code` is preferred when
 * the catalog has one; otherwise the server's message, otherwise a
 * translated generic fallback.
 */
export function errorMessage(error, fallback) {
  const data = error?.response?.data;
  const key = data?.error_code && `errors.${data.error_code}`;
  if (key && i18n.exists(key)) return i18n.t(key);
  return data?.message ?? fallback ?? i18n.t("errors.generic");
}

// "2.00" -> "2", "1.50" -> "1.5"
export function formatQuantity(value) {
  return String(Number(value));
}
