import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import i18n from "../i18n";
import { LANGUAGES } from "../i18n/languages";
import Sheet from "./Sheet";

function GlobeIcon(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
    </svg>
  );
}

/**
 * Language switcher. Each option is written in its own language (a speaker
 * scans for "isiZulu", not "Zulu"), with the English name underneath. Signed
 * in, the choice is saved to the account; signed out, to this browser.
 */
export default function LanguagePicker({ variant = "button", onPicked }) {
  const { t } = useTranslation();
  const { setLanguage } = useAuth();
  const [open, setOpen] = useState(false);
  const current = LANGUAGES.find((l) => l.code === i18n.language) ?? LANGUAGES[0];

  const trigger =
    variant === "row" ? (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-[15px] font-medium text-zinc-800 active:bg-zinc-100"
      >
        <GlobeIcon className="h-5 w-5 text-zinc-400" />
        {t("language.label")}
        <span className="ml-auto text-sm font-normal text-zinc-500">{current.name}</span>
      </button>
    ) : (
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={t("language.change")}
        className="pressable inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[13px] font-medium text-zinc-600 hover:bg-zinc-200/50 hover:text-zinc-900"
      >
        <GlobeIcon className="h-4 w-4" />
        {/* compact: the top bar shows just the globe below laptop width. */}
        <span className={variant === "compact" ? "hidden lg:inline" : undefined}>{current.name}</span>
      </button>
    );

  return (
    <>
      {trigger}
      <Sheet open={open} onClose={() => setOpen(false)} title={t("language.choose")}>
        <ul className="-mx-2 space-y-0.5" role="radiogroup" aria-label={t("language.label")}>
          {LANGUAGES.map((language) => {
            const selected = language.code === current.code;
            return (
              <li key={language.code}>
                <button
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  lang={language.code}
                  onClick={async () => {
                    setOpen(false);
                    await setLanguage(language.code);
                    onPicked?.();
                  }}
                  className={`flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition-colors duration-150 ${
                    selected ? "bg-violet-50" : "hover:bg-zinc-50"
                  }`}
                >
                  <span>
                    <span className={`block text-[15px] font-medium ${selected ? "text-violet-700" : "text-zinc-900"}`}>{language.name}</span>
                    {language.english !== language.name && <span className="block text-xs text-zinc-500">{language.english}</span>}
                  </span>
                  {selected && (
                    <svg viewBox="0 0 16 16" fill="none" className="h-4 w-4 text-violet-600" aria-hidden="true">
                      <path d="M3.5 8.5 6.5 11.5 12.5 4.5" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
        <p className="mt-4 text-xs text-zinc-500">{t("language.reviewNote")}</p>
      </Sheet>
    </>
  );
}
