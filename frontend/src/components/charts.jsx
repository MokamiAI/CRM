import { useState } from "react";
import { formatMoney, formatMoneyCompact, formatMonth } from "../utils/format";

/*
 * Two small charts for the sales dashboard, in plain HTML/CSS.
 * Specs from the dataviz skill: bars <=24px thick with a 4px rounded data
 * end and a square baseline; hairline recessive gridlines; one series, so
 * one colour and no legend (the title names it); text in ink, never in the
 * bar colour; every bar is its own hover/focus target with a tooltip, and
 * every value is also reachable without hovering (labels or a table).
 * Colour #8b5cf6 (violet-500) passes the palette validator on this surface.
 */

const BAR = "bg-violet-500";
const BAR_ACTIVE = "bg-violet-400";

/** "Nice" axis maximum: 1, 2, 2.5 or 5 x a power of ten, at or above max. */
function niceMax(max) {
  if (max <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(max));
  return [1, 2, 2.5, 5, 10].map((m) => m * power).find((m) => m >= max);
}

function Tooltip({ value, label, align = "center" }) {
  const position = align === "end" ? "right-0" : align === "start" ? "left-0" : "left-1/2 -translate-x-1/2";
  return (
    <span className={`pointer-events-none absolute bottom-full z-10 mb-2 whitespace-nowrap rounded-lg bg-zinc-900 px-2.5 py-1.5 text-left shadow-pop ${position}`}>
      {/* Value leads, label follows. */}
      <span className="block text-sm font-semibold text-white">{value}</span>
      <span className="block text-[11px] text-zinc-400">{label}</span>
    </span>
  );
}

/** Monthly columns, e.g. cash collected over the last 6 months. */
export function ColumnChart({ data, ariaLabel }) {
  const [active, setActive] = useState(null);
  const top = niceMax(Math.max(...data.map((d) => Number(d.total)), 0));
  const ticks = [top, top / 2, 0];
  const last = data.length - 1;

  return (
    <figure aria-label={ariaLabel}>
      <div className="flex gap-3">
        {/* Y axis: three clean ticks carry the values not labelled directly. */}
        <div className="flex h-40 w-12 shrink-0 flex-col justify-between text-right text-[11px] tabular-nums text-zinc-400" aria-hidden="true">
          {ticks.map((t) => (
            <span key={t} className="-translate-y-1/2 first:translate-y-0 last:translate-y-0">
              {formatMoneyCompact(t)}
            </span>
          ))}
        </div>
        <div className="relative h-40 flex-1">
          {/* Hairline gridlines, recessive. */}
          {ticks.map((t) => (
            <span key={t} className="absolute inset-x-0 h-px bg-zinc-100" style={{ top: `${(1 - t / top) * 100}%` }} aria-hidden="true" />
          ))}
          <div className="absolute inset-0 flex items-end">
            {data.map((d, i) => {
              const value = Number(d.total);
              const isActive = active === i;
              return (
                // The whole column slot is the hit target, bigger than the bar.
                <button
                  key={d.month}
                  type="button"
                  className="relative flex h-full flex-1 cursor-default items-end justify-center focus:outline-none"
                  onPointerEnter={() => setActive(i)}
                  onPointerLeave={() => setActive(null)}
                  onFocus={() => setActive(i)}
                  onBlur={() => setActive(null)}
                  aria-label={`${formatMonth(d.month, "long")}: ${formatMoney(value)}`}
                >
                  <span
                    className={`relative block w-full max-w-[24px] rounded-t-[4px] transition-colors duration-150 ${isActive ? BAR_ACTIVE : BAR}`}
                    style={{ height: `${Math.max((value / top) * 100, value > 0 ? 1.5 : 0)}%` }}
                  >
                    {/* Selective direct label: only the latest month. */}
                    {i === last && !isActive && value > 0 && (
                      <span className="absolute bottom-full left-1/2 mb-1 -translate-x-1/2 whitespace-nowrap text-[11px] font-medium text-zinc-700">
                        {formatMoneyCompact(value)}
                      </span>
                    )}
                    {isActive && <Tooltip value={formatMoney(value)} label={formatMonth(d.month, "long")} align={i === last ? "end" : i === 0 ? "start" : "center"} />}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <div className="ml-[3.75rem] mt-2 flex" aria-hidden="true">
        {data.map((d) => (
          <span key={d.month} className="flex-1 text-center text-[11px] text-zinc-500">
            {formatMonth(d.month)}
          </span>
        ))}
      </div>
      {/* Table view: every value reachable without hovering. */}
      <table className="sr-only">
        <caption>{ariaLabel}</caption>
        <tbody>
          {data.map((d) => (
            <tr key={d.month}>
              <th scope="row">{formatMonth(d.month, "long")}</th>
              <td>{formatMoney(d.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/** Horizontal bars with direct labels, e.g. pipeline value by stage. */
export function BarList({ rows, ariaLabel }) {
  const [active, setActive] = useState(null);
  const max = Math.max(...rows.map((r) => Number(r.value)), 0) || 1;
  return (
    <figure aria-label={ariaLabel}>
      <ul className="space-y-3">
        {rows.map((r, i) => {
          const value = Number(r.value);
          const pct = (value / max) * 100;
          const isActive = active === i;
          return (
            <li key={r.label} className="grid grid-cols-[5.5rem_minmax(0,1fr)_auto] items-center gap-3 text-sm">
              <span className="truncate text-zinc-600">{r.label}</span>
              <button
                type="button"
                className="relative flex h-7 cursor-default items-center focus:outline-none"
                onPointerEnter={() => setActive(i)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                aria-label={`${r.label}: ${formatMoney(value)}, ${r.detail}`}
              >
                <span
                  className={`relative block h-5 shrink-0 rounded-r-[4px] transition-colors duration-150 ${isActive ? BAR_ACTIVE : BAR}`}
                  style={{ width: `${pct}%`, minWidth: value > 0 ? 3 : 0 }}
                >
                  {isActive && <Tooltip value={formatMoney(value)} label={`${r.label} · ${r.detail}`} align="start" />}
                </span>
              </button>
              {/* Value at the end of the row, in ink: its own column, so it
                  can never run past the card however long the bar is. */}
              <span className="text-right text-xs leading-tight tabular-nums">
                <span className="block font-medium text-zinc-700">{formatMoneyCompact(value)}</span>
                <span className="block text-zinc-400">{r.detail}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </figure>
  );
}
