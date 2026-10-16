// YGT's service worker: shows push messages (reminders, assigned tasks,
// task updates) even when YGT isn't open, and opens the right page when
// one is tapped. Registered by src/utils/push.js; nothing else lives here.

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: event.data ? event.data.text() : "YGT" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "YGT", {
      body: data.body || "",
      icon: "/icon-192.png",
      badge: "/icon-72.png",
      tag: data.tag,
      data: { url: data.url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      // A YGT tab is already open: bring it forward on that page.
      for (const win of windows) {
        if (new URL(win.url).origin === self.location.origin && "focus" in win) {
          win.navigate(url);
          return win.focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
