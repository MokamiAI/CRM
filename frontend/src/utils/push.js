// Push messages on this phone or computer (Web Push). The browser asks the
// person once; YGT then keeps the subscription on the server, so reminders
// and tasks reach them even when YGT isn't open.
import apiClient from "../services/apiClient";

export function pushSupported() {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

/** "on", "off", "blocked" (the person said no in the browser), or
 *  "unsupported" (an old browser, or iPhone Safari outside the home screen). */
export async function pushState() {
  if (!pushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "blocked";
  const reg = await navigator.serviceWorker.getRegistration("/sw.js");
  const sub = await reg?.pushManager.getSubscription();
  return sub && Notification.permission === "granted" ? "on" : "off";
}

function keyBytes(base64url) {
  const padded = (base64url + "===".slice((base64url.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

/** Asks the browser, subscribes, and tells the server. Returns the new state. */
export async function enablePush() {
  if (!pushSupported()) return "unsupported";
  const { data } = await apiClient.get("/notifications/push");
  if (!data.enabled || !data.public_key) return "unavailable";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "blocked" : "off";
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(data.public_key) });
  const json = sub.toJSON();
  await apiClient.post("/notifications/push", { endpoint: json.endpoint, keys: json.keys });
  return "on";
}

export async function disablePush() {
  const reg = await navigator.serviceWorker?.getRegistration("/sw.js");
  const sub = await reg?.pushManager.getSubscription();
  if (sub) {
    await apiClient.post("/notifications/push/remove", { endpoint: sub.endpoint }).catch(() => {});
    await sub.unsubscribe();
  }
  return "off";
}

/** Already allowed: renew the subscription with the server quietly
 *  (subscriptions can change; this keeps the server's copy current). */
export async function refreshPush() {
  if ((await pushState()) === "on") await enablePush().catch(() => {});
}
