// Dhanz GPT service worker: shows push notifications (scheduled task results) and opens
// the chat when one is clicked. It does no caching.
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "Dhanz GPT", body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Dhanz GPT", {
      body: data.body || "",
      tag: data.tag,
      data: { url: typeof data.url === "string" && data.url.startsWith("/") ? data.url : "/scheduled" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/scheduled", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      const same = wins.find((w) => w.url === url);
      if (same) return same.focus();
      return self.clients.openWindow(url);
    }),
  );
});
