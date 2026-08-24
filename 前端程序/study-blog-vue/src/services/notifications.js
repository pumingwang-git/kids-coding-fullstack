import { request } from "./auth";

export function listNotifications({ tab = "all", page = 1, pageSize = 20 } = {}) {
  const params = new URLSearchParams({ tab, page: String(page), page_size: String(pageSize) });
  return request(`/api/student/notifications?${params}`);
}

export function unreadNotificationCount() {
  return request("/api/student/notifications/unread-count");
}

export function markNotificationRead(notificationId) {
  return request(`/api/student/notifications/${notificationId}/read`, {
    method: "POST",
    body: "{}",
  });
}

export function markAllNotificationsRead() {
  return request("/api/student/notifications/read-all", { method: "POST", body: "{}" });
}
