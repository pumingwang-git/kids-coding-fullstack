import { request } from "./auth";

function query(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value != null) search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function fetchPracticeTasks(params) {
  return request(`/api/student/practice${query(params)}`);
}

export function fetchHomeworkTasks(params) {
  return request(`/api/student/homework${query(params)}`);
}

export function fetchExamTasks(params) {
  return request(`/api/student/exams${query(params)}`);
}

export function fetchTaskOverview() {
  return request("/api/student/tasks/overview");
}
