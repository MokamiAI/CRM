import i18n from "../i18n";
import { intlLocale } from "../i18n/languages";

// The company currency lives in /settings, which is ADMIN-only, so the UI
// formats with the deployment default. Matches DEFAULT_CURRENCY in .env.
export const CURRENCY = import.meta.env.VITE_CURRENCY || "ZAR";

// Formatters follow the current UI language (falling back to en-ZA where
// the browser lacks locale data; see intlLocale). Intl formatters are
// costly to build, so one is cached per locale + options.
const cache = new Map();
function formatter(Kind, options) {
  const locale = intlLocale(i18n.language);
  const key = `${Kind.name}|${locale}|${JSON.stringify(options)}`;
  if (!cache.has(key)) cache.set(key, new Kind(locale, options));
  return cache.get(key);
}

// API amounts are Decimal strings ("1500.00"); never do maths on them as
// floats beyond display and simple sums.
export function formatMoney(value) {
  const amount = Number(value ?? 0);
  return formatter(Intl.NumberFormat, { style: "currency", currency: CURRENCY, minimumFractionDigits: 2 }).format(
    Number.isFinite(amount) ? amount : 0
  );
}

// Prices on plan cards: "R 149", "R 1 490" (no cents).
export function formatMoneyWhole(value) {
  return formatter(Intl.NumberFormat, { style: "currency", currency: CURRENCY, maximumFractionDigits: 0 }).format(Number(value ?? 0));
}

// Axis ticks and tight spaces: "R 185k", "R 1,2M".
export function formatMoneyCompact(value) {
  return formatter(Intl.NumberFormat, { style: "currency", currency: CURRENCY, notation: "compact", maximumFractionDigits: 1 }).format(
    Number(value ?? 0)
  );
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
