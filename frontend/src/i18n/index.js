import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { LANGUAGE_CODES } from "./languages";

import en from "./locales/en.json";

// English is built in (it's also the fallback for anything missing). Every
// other language is its own file, fetched the first time someone picks it,
// so a phone doesn't download all eleven to show one. The Capacitor app
// ships these files inside the app, so it still works offline.
const loaders = import.meta.glob(["./locales/*.json", "!./locales/en.json"], { import: "default" });

const STORAGE_KEY = "language";

function storedLanguage() {
  try {
    const code = localStorage.getItem(STORAGE_KEY);
    return LANGUAGE_CODES.includes(code) ? code : null;
  } catch {
    return null;
  }
}

// ---------- "Customers" or "Clients" ----------
// A company setting picks the word. Rather than a second copy of every
// string, this post-processor swaps the word in place. Only languages whose
// catalog uses a word that means "customer" but not "client" need a rule:
// Afrikaans "kliënt" already covers both, and the Sotho, Tswana, Venda,
// Tsonga, Swati and Xhosa catalogs use "buyer" words that do too. The Nguni
// stems below keep the same noun class, so the surrounding grammar still agrees.
const CLIENT_RULES = {
  en: [[/\b([Cc])ustomer/g, (_m, c) => (c === "C" ? "Client" : "client")]],
  zu: [[/khasimende/g, "klayenti"]],
  nr: [[/khasimende/g, "klayenti"]],
};
const TERM_KEY = "customerTerm";
let customerTerm = (() => {
  try {
    return localStorage.getItem(TERM_KEY) === "client" ? "client" : "customer";
  } catch {
    return "customer";
  }
})();

export function getCustomerTerm() {
  return customerTerm;
}

/** Apply the company's wording; returns true when it changed. */
export function setCustomerTerm(term) {
  const next = term === "client" ? "client" : "customer";
  if (next === customerTerm) return false;
  customerTerm = next;
  try {
    localStorage.setItem(TERM_KEY, next);
  } catch {
    /* falls back to "customer" until the company settings load */
  }
  i18n.emit("customerTermChanged", next);
  return true;
}

i18n.use({
  type: "postProcessor",
  name: "customerTerm",
  process(value, _key, options, translator) {
    if (customerTerm !== "client" || typeof value !== "string") return value;
    const rules = CLIENT_RULES[options?.lng ?? translator?.language] ?? [];
    return rules.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), value);
  },
});

i18n.use({
  type: "backend",
  read(language, _namespace, callback) {
    const load = loaders[`./locales/${language}.json`];
    if (!load) return callback(null, {});
    load().then(
      (translation) => callback(null, translation),
      (error) => callback(error, null)
    );
  },
});

// main.jsx waits for this, so the first screen is already in the right language.
export const i18nReady = i18n.use(initReactI18next).init({
  postProcess: ["customerTerm"],
  resources: { en: { translation: en } },
  partialBundledLanguages: true,
  // Languages load before they're switched to (changeLanguage waits), so
  // components never need to suspend for a translation.
  react: { useSuspense: false },
  // Before sign-in we only know what this browser last used; after sign-in
  // the user's saved preference wins (AuthContext applies it).
  lng: storedLanguage() ?? "en",
  fallbackLng: "en",
  supportedLngs: LANGUAGE_CODES,
  interpolation: { escapeValue: false }, // React already escapes
  // A missing or empty translation shows the English text, never a raw key.
  returnEmptyString: false,
});

i18n.on("languageChanged", (code) => {
  document.documentElement.lang = code;
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* private mode: the server-side preference still applies after sign-in */
  }
});
document.documentElement.lang = i18n.language;

export default i18n;
