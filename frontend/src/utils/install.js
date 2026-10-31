// "Install YGT": a shortcut on the desktop and taskbar (or a phone's home
// screen) that opens YGT in its own window, like any app. Chrome and Edge
// offer it through an event we keep until the person clicks our button;
// Safari has no such event, so there we explain the menu steps instead.

let deferred = null;
const listeners = new Set();
const notify = () => listeners.forEach((fn) => fn());

// Once YGT is installed on this device we stop asking. Browsers only tell
// us some of the time (Apple's never do), so we also remember it: when YGT
// opens as the app, when the browser says it was installed, or when someone
// on an iPhone taps "I've already added it".
const INSTALLED = "ygt.appInstalled";

function remembered() {
  try {
    return localStorage.getItem(INSTALLED) === "1";
  } catch {
    return false;
  }
}

export function markInstalled() {
  try {
    localStorage.setItem(INSTALLED, "1");
  } catch {
    // Private window: we just ask again next visit.
  }
  deferred = null;
  notify();
}

/** Inside the Capacitor phone app: it's already an app. */
export function isNativeApp() {
  return Boolean(window.Capacitor?.isNativePlatform?.());
}

/** Opened from the installed shortcut, not a browser tab. */
export function isInstalled() {
  return window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

export function isIOS() {
  const ua = navigator.userAgent;
  // iPadOS reports itself as a Mac; touch gives it away.
  return /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
}

/** Safari on a Mac: File › Add to Dock. */
export function isMacSafari() {
  const ua = navigator.userAgent;
  return !isIOS() && /Macintosh/.test(ua) && /Safari/.test(ua) && !/Chrome|Chromium|CriOS|Edg|Firefox|OPR/.test(ua);
}

export function isPhone() {
  return isIOS() || /Android|Mobi/.test(navigator.userAgent);
}

/** "prompt" (we can show the browser's install dialog), "ios" or
 *  "mac-safari" (menu steps), or null (installed, native, or not offered). */
export function installMode() {
  if (isNativeApp() || isInstalled() || remembered()) return null;
  if (deferred) return "prompt";
  if (isIOS()) return "ios";
  if (isMacSafari()) return "mac-safari";
  return null;
}

export function onInstallChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Shows the browser's install dialog. True if they installed. */
export async function promptInstall() {
  if (!deferred) return false;
  const event = deferred;
  deferred = null;
  event.prompt();
  const { outcome } = await event.userChoice;
  notify();
  return outcome === "accepted";
}

if (typeof window !== "undefined" && !isNativeApp()) {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault(); // our bar asks, not the browser's own pop-up
    deferred = event;
    // Offered again: it was uninstalled, so forget that it was there.
    try {
      localStorage.removeItem(INSTALLED);
    } catch {
      // nothing to forget
    }
    notify();
  });
  window.addEventListener("appinstalled", markInstalled);
  if (isInstalled()) markInstalled();
  // Chrome and Edge can say whether this site is installed on the device
  // (manifest.webmanifest lists it under related_applications).
  navigator.getInstalledRelatedApps?.().then((apps) => apps.length > 0 && markInstalled()).catch(() => {});
  // Same worker that push alerts use; some browsers want one before they
  // treat the site as installable.
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
  }
}
