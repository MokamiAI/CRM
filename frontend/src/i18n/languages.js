// South Africa's 11 official spoken languages. `name` is how the language
// names itself (what a speaker looks for in a picker); `english` is for
// screen-reader context; `intl` is the locale tag for number/date formats.
export const LANGUAGES = [
  { code: "en", name: "English", english: "English", intl: "en-ZA" },
  { code: "af", name: "Afrikaans", english: "Afrikaans", intl: "af-ZA" },
  { code: "zu", name: "isiZulu", english: "Zulu", intl: "zu-ZA" },
  { code: "xh", name: "isiXhosa", english: "Xhosa", intl: "xh-ZA" },
  { code: "nso", name: "Sepedi", english: "Northern Sotho", intl: "nso-ZA" },
  { code: "tn", name: "Setswana", english: "Tswana", intl: "tn-ZA" },
  { code: "st", name: "Sesotho", english: "Southern Sotho", intl: "st-ZA" },
  { code: "ts", name: "Xitsonga", english: "Tsonga", intl: "ts-ZA" },
  { code: "ss", name: "siSwati", english: "Swati", intl: "ss-ZA" },
  { code: "ve", name: "Tshivenḓa", english: "Venda", intl: "ve-ZA" },
  { code: "nr", name: "isiNdebele", english: "Southern Ndebele", intl: "nr-ZA" },
];

export const LANGUAGE_CODES = LANGUAGES.map((l) => l.code);

const supported = new Map();

/**
 * The Intl locale to format numbers and dates with. Browsers ship full
 * locale data for English, Afrikaans, isiZulu and (mostly) isiXhosa; for
 * the others they may not, and an unsupported tag silently formats like
 * the browser default, possibly not South African. Falling back to en-ZA
 * keeps SA conventions (R 1 234,56, day-month-year) either way.
 */
export function intlLocale(code) {
  if (supported.has(code)) return supported.get(code);
  const tag = LANGUAGES.find((l) => l.code === code)?.intl ?? "en-ZA";
  const ok = Intl.DateTimeFormat.supportedLocalesOf([tag]).length > 0 && Intl.NumberFormat.supportedLocalesOf([tag]).length > 0;
  const resolved = ok ? tag : "en-ZA";
  supported.set(code, resolved);
  return resolved;
}
