import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

const EXIT_MS = 200; // matches the closed-state durations in index.css

/**
 * Bottom sheet on phones, centered dialog on larger screens (index.css).
 *
 * Stays mounted through its exit transition: `open` false flips
 * data-state to "closed" first, and the DOM goes away once the panel has
 * animated out. CSS transitions rather than keyframes, so opening and
 * closing quickly retargets smoothly instead of restarting from zero.
 */
export default function Sheet({ open, onClose, title, children, footer }) {
  const { t } = useTranslation();
  const [mounted, setMounted] = useState(open);
  const [state, setState] = useState("closed");
  const panelRef = useRef(null);

  useEffect(() => {
    if (open) {
      setMounted(true);
      // Two frames: the first commits the closed styles, the second
      // transitions away from them. One frame can get batched together.
      const frame = requestAnimationFrame(() =>
        requestAnimationFrame(() => setState("open"))
      );
      return () => cancelAnimationFrame(frame);
    }
    setState("closed");
    const timer = setTimeout(() => setMounted(false), EXIT_MS);
    return () => clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [open, onClose]);

  // Focus the first field once the panel is in place. Done by hand rather
  // than autoFocus: on a phone, focusing mid-animation opens the keyboard
  // while the sheet is still sliding, which jumps the layout.
  useEffect(() => {
    if (state !== "open") return;
    const timer = setTimeout(() => {
      const field = panelRef.current?.querySelector("input, select, textarea");
      if (field && window.matchMedia("(pointer: fine)").matches) field.focus();
    }, 220);
    return () => clearTimeout(timer);
  }, [state]);

  if (!mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-40 flex items-end justify-center sm:items-center sm:p-6">
      <div
        className="sheet-overlay absolute inset-0 bg-zinc-900/40"
        data-state={state}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        data-state={state}
        className="sheet-panel relative flex max-h-[90dvh] w-full flex-col rounded-t-2xl bg-white shadow-xl sm:max-w-lg sm:rounded-2xl"
      >
        <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-4">
          <h2 className="text-base font-semibold text-zinc-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="pressable -mr-2 rounded-lg p-2 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600"
            aria-label={t("common.close")}
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        </div>
        <div className="sheet-content flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div
            className="flex justify-end gap-2 border-t border-zinc-100 px-5 py-3"
            style={{ paddingBottom: "max(env(safe-area-inset-bottom, 0px), 0.75rem)" }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
