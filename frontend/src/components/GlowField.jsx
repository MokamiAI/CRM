import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

const TYPING_HOLD_MS = 500;

/**
 * An input wrapped in an animated colour ring: the ring travels the border
 * while the field has focus, and the halo brightens as you type. For the
 * sign-in screen only: seen once a day, so the flourish is earned there;
 * on in-app forms used all day it would wear thin. Styles in index.css.
 *
 * Password fields get a show/hide button, so people can check what they
 * typed before a wrong password locks them out of a sign-in.
 */
export default function GlowField({ onChange, type, ...inputProps }) {
  const { t } = useTranslation();
  const [typing, setTyping] = useState(false);
  const [visible, setVisible] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  const isPassword = type === "password";

  return (
    <div className="glow-field" data-typing={typing}>
      <span className="glow-field__halo" aria-hidden="true" />
      <span className="glow-field__clip" aria-hidden="true">
        <span className="glow-field__ring" />
      </span>
      <input
        {...inputProps}
        type={isPassword && visible ? "text" : type}
        className={isPassword ? "input !pr-11" : "input"}
        onChange={(event) => {
          onChange?.(event);
          setTyping(true);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => setTyping(false), TYPING_HOLD_MS);
        }}
      />
      {isPassword && (
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={t(visible ? "password.hide" : "password.show")}
          aria-pressed={visible}
          title={t(visible ? "password.hide" : "password.show")}
          className="pressable absolute inset-y-0 right-1 my-auto flex h-9 w-9 items-center justify-center rounded-lg text-zinc-400 hover:text-zinc-700 focus-visible:outline-2 focus-visible:outline-indigo-500"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5" aria-hidden="true">
            <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
            <circle cx="12" cy="12" r="2.8" />
            {visible && <path d="M4 4l16 16" />}
          </svg>
        </button>
      )}
    </div>
  );
}
