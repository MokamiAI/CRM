import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function Button({ variant = "primary", className = "", ...props }) {
  return <button type="button" className={`btn btn-${variant} ${className}`} {...props} />;
}

export function ButtonLink({ variant = "primary", className = "", ...props }) {
  return <Link className={`btn btn-${variant} ${className}`} {...props} />;
}

export function PlusIcon(props) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" {...props}>
      <path d="M8.75 3.75a.75.75 0 0 0-1.5 0v3.5h-3.5a.75.75 0 0 0 0 1.5h3.5v3.5a.75.75 0 0 0 1.5 0v-3.5h3.5a.75.75 0 0 0 0-1.5h-3.5v-3.5Z" />
    </svg>
  );
}

export function Field({ label, hint, error, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="label">{label}</span>
      {children}
      {error ? (
        <span className="mt-1.5 block text-xs text-red-600">{error}</span>
      ) : hint ? (
        <span className="mt-1.5 block text-xs text-zinc-500">{hint}</span>
      ) : null}
    </label>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
      <div className="min-w-0">
        {eyebrow && <div className="mb-2">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold text-zinc-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex max-w-full flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

// Status is shown as a dot + label, never color alone.
const STATUS_STYLES = {
  draft: ["bg-zinc-100 text-zinc-600 ring-zinc-200", "bg-zinc-400"],
  sent: ["bg-sky-50 text-sky-700 ring-sky-200/70", "bg-sky-500"],
  partially_paid: ["bg-amber-50 text-amber-700 ring-amber-200/70", "bg-amber-500"],
  paid: ["bg-emerald-50 text-emerald-700 ring-emerald-200/70", "bg-emerald-500"],
  overdue: ["bg-red-50 text-red-700 ring-red-200/70", "bg-red-500"],
  void: ["bg-zinc-50 text-zinc-400 ring-zinc-200", "bg-zinc-300"],
  accepted: ["bg-emerald-50 text-emerald-700 ring-emerald-200/70", "bg-emerald-500"],
  rejected: ["bg-red-50 text-red-700 ring-red-200/70", "bg-red-500"],
  expired: ["bg-zinc-100 text-zinc-500 ring-zinc-200", "bg-zinc-400"],
  converted: ["bg-violet-50 text-violet-700 ring-violet-200/70", "bg-violet-500"],
  won: ["bg-emerald-50 text-emerald-700 ring-emerald-200/70", "bg-emerald-500"],
  lost: ["bg-red-50 text-red-700 ring-red-200/70", "bg-red-500"],
  active: ["bg-emerald-50 text-emerald-700 ring-emerald-200/70", "bg-emerald-500"],
  inactive: ["bg-zinc-100 text-zinc-500 ring-zinc-200", "bg-zinc-400"],
  scheduled: ["bg-indigo-50 text-indigo-700 ring-indigo-200/70", "bg-indigo-500"],
  sending: ["bg-amber-50 text-amber-700 ring-amber-200/70", "bg-amber-500 animate-pulse"],
  failed: ["bg-red-50 text-red-700 ring-red-200/70", "bg-red-500"],
  queued: ["bg-zinc-100 text-zinc-600 ring-zinc-200", "bg-zinc-400"],
};

export function StatusBadge({ status }) {
  const { t } = useTranslation();
  const [badge, dot] = STATUS_STYLES[status] ?? STATUS_STYLES.draft;
  const label = t(`status.${status}`);
  // Animate only a real change (Sent -> Paid), never the first render: a
  // list of 50 badges fading in on every visit would just be noise.
  // The ref is updated after commit (not during render) so StrictMode's
  // double render can't swallow the change.
  const previous = useRef(status);
  const changed = previous.current !== status;
  useEffect(() => {
    previous.current = status;
  }, [status]);
  return (
    <span
      key={status}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${badge} ${changed ? "badge-swap" : ""}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden="true" />
      {label}
    </span>
  );
}

// Initials on a soft tint, picked from the name so a customer keeps the
// same color everywhere. Identity aid only; the name is always beside it.
const AVATAR_TINTS = [
  "bg-sky-100 text-sky-700",
  "bg-violet-100 text-violet-700",
  "bg-amber-100 text-amber-800",
  "bg-emerald-100 text-emerald-700",
  "bg-rose-100 text-rose-700",
  "bg-indigo-100 text-indigo-700",
  "bg-teal-100 text-teal-700",
];

export function Avatar({ name = "?", size = "md" }) {
  const words = name.replace(/\(.*?\)/g, "").trim().split(/\s+/);
  const initials = ((words[0]?.[0] ?? "?") + (words[1]?.[0] ?? "")).toUpperCase();
  let hash = 0;
  for (const ch of name) hash = (Math.imul(hash ^ ch.charCodeAt(0), 0x9e3779b1) >>> 0);
  const sizeClass = { sm: "h-7 w-7 text-[11px]", md: "h-9 w-9 text-xs", lg: "h-14 w-14 text-base" }[size];
  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${sizeClass} ${
        AVATAR_TINTS[hash % AVATAR_TINTS.length]
      }`}
    >
      {initials}
    </span>
  );
}

export function EmptyState({ title, description, action, icon, art, plain = false }) {
  // plain: no card of its own, for empty states inside a pane that already is one.
  return (
    <div className={`${plain ? "" : "card"} flex flex-col items-center px-6 py-14 text-center`}>
      {art ? (
        <div className="mb-4">{art}</div>
      ) : (
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-zinc-200 bg-zinc-50 text-zinc-400 shadow-xs">
          {icon ?? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className="h-5 w-5">
              <path d="M4 7h16M4 12h10M4 17h7" strokeLinecap="round" />
            </svg>
          )}
        </div>
      )}
      <p className="font-medium text-zinc-900">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-zinc-500">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  const { t } = useTranslation();
  return (
    <div className="card px-6 py-10 text-center">
      <p className="text-sm text-zinc-600">{message ?? t("common.loadError")}</p>
      {onRetry && (
        <Button variant="secondary" className="mt-4" onClick={onRetry}>
          {t("common.tryAgain")}
        </Button>
      )}
    </div>
  );
}

// Skeleton rows in the shape of the list they stand in for, so the layout
// doesn't jump when data arrives.
export function ListSkeleton({ rows = 5 }) {
  const { t } = useTranslation();
  return (
    <div className="card divide-y divide-zinc-100" aria-busy="true" aria-label={t("common.loading")}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-5 py-4">
          <div className="h-9 w-9 animate-pulse rounded-full bg-zinc-100" />
          <div className="flex-1 space-y-2">
            <div className="h-3.5 w-40 animate-pulse rounded bg-zinc-100" />
            <div className="h-3 w-24 animate-pulse rounded bg-zinc-100" />
          </div>
          <div className="h-3.5 w-16 animate-pulse rounded bg-zinc-100" />
        </div>
      ))}
    </div>
  );
}

// Segmented filter. Native horizontal scroll on narrow screens (no JS
// gesture), so the browser keeps its own touch physics. The active state
// switches instantly: filters are clicked often, motion would only slow it.
export function FilterChips({ options, value, onChange }) {
  return (
    <div className="-mx-4 mb-4 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:px-0">
      <div className="inline-flex gap-1 rounded-lg border border-zinc-200/80 bg-zinc-100/70 p-1">
        {options.map((option) => {
          const active = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(option.value)}
              className={`pressable shrink-0 whitespace-nowrap rounded-md px-3 py-1.5 text-[13px] font-medium ${
                active ? "bg-white text-zinc-900 shadow-xs ring-1 ring-zinc-200/80" : "text-zinc-500 hover:text-zinc-800"
              }`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function SearchInput({ value, onChange, placeholder }) {
  return (
    <div className="relative mb-4">
      <svg
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
      >
        <path
          fillRule="evenodd"
          d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.45 4.39l3.08 3.08a.75.75 0 1 1-1.06 1.06l-3.08-3.08A7 7 0 0 1 2 9Z"
          clipRule="evenodd"
        />
      </svg>
      <input
        type="search"
        enterKeyHint="search"
        className="input pl-9"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}


// Shared across every tooltip: once one has been shown, the next one the
// pointer reaches opens instantly (no delay, no motion), which makes a row
// of icon buttons feel fast to scan.
let openTooltips = 0;
let lastClosedAt = 0;
const TOOLTIP_DELAY_MS = 450;
const TOOLTIP_WARM_MS = 400;

const TOOLTIP_SIDES = {
  top: { position: "bottom-full left-1/2 mb-2 -translate-x-1/2", origin: "bottom center" },
  // For controls near the right edge: anchor the tooltip's right side to
  // the trigger so it can't hang off-screen (an invisible tooltip still
  // counts toward page width and would add a sideways scroll).
  "top-end": { position: "bottom-full right-0 mb-2", origin: "bottom right" },
  bottom: { position: "top-full left-1/2 mt-2 -translate-x-1/2", origin: "top center" },
  right: { position: "left-full top-1/2 ml-2 -translate-y-1/2", origin: "left center" },
};

/** Label for an icon-only control. Mouse/trackpad only: touch has no hover. */
export function Tooltip({ label, side = "top", children }) {
  const [open, setOpen] = useState(false);
  const [instant, setInstant] = useState(false);
  const timer = useRef(null);

  const show = (immediately) => {
    clearTimeout(timer.current);
    const warm = openTooltips > 0 || Date.now() - lastClosedAt < TOOLTIP_WARM_MS;
    const reveal = () => {
      openTooltips += 1;
      setInstant(warm || immediately);
      setOpen(true);
    };
    if (warm || immediately) reveal();
    else timer.current = setTimeout(reveal, TOOLTIP_DELAY_MS);
  };
  const hide = () => {
    clearTimeout(timer.current);
    if (open) {
      openTooltips = Math.max(0, openTooltips - 1);
      lastClosedAt = Date.now();
    }
    setOpen(false);
  };
  useEffect(() => () => clearTimeout(timer.current), []);

  const { position, origin } = TOOLTIP_SIDES[side];
  return (
    <span
      className="relative inline-flex"
      onPointerEnter={(e) => e.pointerType === "mouse" && show(false)}
      onPointerLeave={hide}
      onFocus={(e) => e.target.matches(":focus-visible") && show(true)}
      onBlur={hide}
    >
      {children}
      {/* Outer span positions (translate), inner span animates (scale):
          one element can't do both without the transforms fighting. */}
      <span className={`pointer-events-none absolute z-50 ${position}`}>
        <span
          role="tooltip"
          data-open={open}
          data-instant={instant}
          style={{ transformOrigin: origin }}
          className="tooltip block whitespace-nowrap rounded-md bg-zinc-900 px-2 py-1 text-xs font-medium text-white shadow-pop"
        >
          {label}
        </span>
      </span>
    </span>
  );
}
