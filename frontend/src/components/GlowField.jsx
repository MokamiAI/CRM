import { useEffect, useRef, useState } from "react";

const TYPING_HOLD_MS = 500;

/**
 * An input wrapped in an animated colour ring: the ring travels the border
 * while the field has focus, and the halo brightens as you type. For the
 * sign-in screen only: seen once a day, so the flourish is earned there;
 * on in-app forms used all day it would wear thin. Styles in index.css.
 */
export default function GlowField({ onChange, ...inputProps }) {
  const [typing, setTyping] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  return (
    <div className="glow-field" data-typing={typing}>
      <span className="glow-field__halo" aria-hidden="true" />
      <span className="glow-field__clip" aria-hidden="true">
        <span className="glow-field__ring" />
      </span>
      <input
        {...inputProps}
        className="input"
        onChange={(event) => {
          onChange?.(event);
          setTyping(true);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => setTyping(false), TYPING_HOLD_MS);
        }}
      />
    </div>
  );
}
