import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import { installMode, isPhone, markInstalled, onInstallChange, promptInstall } from "../utils/install";
import { enablePush, pushState } from "../utils/push";

// Closed with ×: asked again after this long.
const SNOOZE = 30 * 24 * 3600 * 1000;

function snoozed(kind) {
  try {
    return Date.now() - Number(localStorage.getItem(`getApp.closed.${kind}`) || 0) < SNOOZE;
  } catch {
    return false;
  }
}

function snooze(kind) {
  try {
    localStorage.setItem(`getApp.closed.${kind}`, String(Date.now()));
  } catch {
    // Private window: it just comes back next visit.
  }
}

/** The blue bar across the top of the app: first "install YGT" (a desktop
 *  and taskbar shortcut, or the home screen on a phone), then, once that's
 *  done or can't be offered, "turn on alerts". One at a time; × hides it
 *  for a month. */
export default function GetTheAppBanner() {
  const { t } = useTranslation();
  const [install, setInstall] = useState(() => installMode());
  const [push, setPush] = useState("checking");
  const [busy, setBusy] = useState(false);
  const [, rerender] = useState(0);

  useEffect(() => onInstallChange(() => setInstall(installMode())), []);
  useEffect(() => {
    pushState().then(setPush).catch(() => setPush("unsupported"));
  }, []);

  const kind = install && !snoozed("install") ? "install" : push === "off" && !snoozed("alerts") ? "alerts" : null;
  if (!kind) return null;

  function close() {
    snooze(kind);
    rerender((n) => n + 1);
  }

  async function act() {
    setBusy(true);
    try {
      if (kind === "install") {
        if (await promptInstall()) toast.success(t("getApp.installed"));
      } else {
        const next = await enablePush();
        setPush(next);
        if (next === "on") {
          await apiClient.post("/notifications/test");
          toast.success(t("notify.pushOn"));
        } else if (next !== "off") {
          toast.message(t(`notify.push.${next}`));
        }
      }
    } catch {
      toast.error(t(kind === "install" ? "getApp.failed" : "notify.push.failed"));
    } finally {
      setBusy(false);
    }
  }

  const phone = isPhone();
  let text;
  let button = null;
  if (kind === "alerts") {
    text = t("getApp.alertsText");
    button = t("getApp.alertsButton");
  } else if (install === "ios") {
    text = t("getApp.iosText");
  } else if (install === "mac-safari") {
    text = t("getApp.macSafariText");
  } else {
    text = t(phone ? "getApp.phoneText" : "getApp.desktopText");
    button = t(phone ? "getApp.phoneButton" : "getApp.desktopButton");
  }

  return (
    <div
      className="-mx-4 -mt-5 mb-5 flex items-center gap-3 bg-indigo-600 px-4 py-2.5 text-white md:-mx-6 md:-mt-6 md:mb-6 md:px-6 lg:-mx-8 lg:px-8"
      role="region"
      aria-label={t(kind === "alerts" ? "getApp.alertsLabel" : "getApp.installLabel")}
    >
      <div className="flex min-w-0 flex-1 flex-wrap items-center justify-center gap-x-4 gap-y-2">
        <p className="text-center text-sm font-medium leading-snug">{text}</p>
        {(install === "ios" || install === "mac-safari") && kind === "install" && (
          <button
            type="button"
            onClick={markInstalled}
            className="pressable inline-flex h-9 shrink-0 items-center rounded-lg px-3.5 text-sm font-semibold ring-1 ring-inset ring-white/70 transition-colors hover:bg-white/10"
          >
            {t("getApp.alreadyAdded")}
          </button>
        )}
        {button && (
          <button
            type="button"
            disabled={busy}
            onClick={act}
            className="pressable inline-flex h-9 shrink-0 items-center gap-2 rounded-lg px-3.5 text-sm font-semibold ring-1 ring-inset ring-white/70 transition-colors hover:bg-white/10 disabled:opacity-60"
          >
            {kind === "alerts" ? <BellIcon /> : <DownloadIcon />}
            {button}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={close}
        aria-label={t("getApp.close")}
        className="pressable -mr-1.5 shrink-0 rounded-lg p-1.5 text-white/85 transition-colors hover:bg-white/10 hover:text-white"
      >
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className="h-5 w-5" aria-hidden="true">
          <path d="M5 5l10 10M15 5L5 15" />
        </svg>
      </button>
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
      <path d="M10 3v9m0 0-3.5-3.5M10 12l3.5-3.5M4 14.5V16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-1.5" />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
      <path d="M5 8a5 5 0 0 1 10 0c0 4.5 2 5.5 2 5.5H3S5 12.5 5 8Zm3.5 8a1.6 1.6 0 0 0 3 0" />
    </svg>
  );
}
