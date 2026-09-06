// 学员端考试接口封装。与 auth.js 同构：credentials: "include"、写操作带 CSRF 头、
// 中文错误文案、401 续期一次再重试。
//
// 这里曾经**故意不做 401 续期**，理由写的是"考试中被登出应该明确暴露出来"。那条推理
// 是反的（2026-08-07 实测推翻）：access_token 的 cookie max-age 只有 15 分钟，考试中
// 又没有任何导航会触发续期，所以一场 90 分钟的考试必然在第 15 分钟集体 401——自动保存
// 报错、交卷失败，正是那条注释担心的"我明明在做题却交不上卷"。不续期是这个现象的成因，
// 不是防线。
//
// 续期也盖不住真正的登出：会话被吊销时 /refresh 自己就会失败，401 照样浮上来。
import { refreshSession } from "./auth";
import { beginRequest, completeRequest, failRequest } from "./runtimeLogger";

const apiBase = import.meta.env.VITE_API_BASE_URL || "";

function cookie(name) {
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=");
}

async function csrfToken(forceRefresh = false) {
  const existing = !forceRefresh && cookie("csrf_token");
  if (existing) return decodeURIComponent(existing);
  const response = await fetch(`${apiBase}/api/auth/csrf`, { credentials: "include" });
  if (!response.ok)
    throw new ExamError("获取会话安全令牌失败，请刷新页面后重试。", response.status);
  const token = cookie("csrf_token");
  if (!token) throw new ExamError("未获取到会话安全令牌，请确认前端与接口使用同一地址访问。", 0);
  return decodeURIComponent(token);
}

export class ExamError extends Error {
  constructor(message, status, code = null) {
    super(message);
    this.name = "ExamError";
    this.status = status;
    // 服务端给的结构化错误码（如 judge_pending）。前端把"已封卷"的 409 当跳结果页
    // 的信号，而"判题没跑完"也是 409 但要留在原地——光靠 status 分不开这两种。
    this.code = code;
  }
}

function errorMessage(body) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => item?.msg).filter(Boolean);
    if (messages.length) return messages.join("；");
  }
  if (detail && typeof detail === "object" && typeof detail.message === "string")
    return detail.message;
  return "请求失败，请稍后再试。";
}

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const isMutation = options.method && options.method !== "GET";
  if (isMutation) headers["X-CSRF-Token"] = await csrfToken();

  const url = `${apiBase}/api/exam${path}`;
  const context = beginRequest(url);
  const send = () =>
    fetch(url, { credentials: "include", ...options, headers: { ...headers, "X-Request-ID": context.id } });
  let response;
  try {
    response = await send();
  } catch (error) {
    failRequest(context, url, error);
    throw error;
  }
  let body = response.status === 204 ? null : await response.json().catch(() => ({}));

  // CSRF cookie 会随会话轮换；重取一次再试，避免作答中途因为换了 token 而存不上。
  if (isMutation && response.status === 403 && body?.detail === "CSRF 校验失败。") {
    headers["X-CSRF-Token"] = await csrfToken(true);
    response = await send();
    body = response.status === 204 ? null : await response.json().catch(() => ({}));
  }
  // access_token 只活 15 分钟，而一场考试可以有 90 分钟。续期一次再重试；
  // 续期失败（会话真被吊销）就保留原始 401，交给调用方跳登录。
  if (response.status === 401) {
    try {
      await refreshSession();
      // 续期会轮换 csrf cookie，写操作必须重新取，否则重试撞 403
      if (isMutation) headers["X-CSRF-Token"] = await csrfToken(true);
      response = await send();
      body = response.status === 204 ? null : await response.json().catch(() => ({}));
    } catch {
      // 保留原始 401
    }
  }
  if (!response.ok) {
    const error = new ExamError(errorMessage(body), response.status, body?.detail?.code ?? null);
    failRequest(context, url, error);
    throw error;
  }
  completeRequest(context, url, response.status);
  return body;
}

export function fetchEntry(token) {
  return request(`/${encodeURIComponent(token)}`);
}

export function fetchLessonHomeworkEntry(lessonId, blockId) {
  return request(`/lesson-homework/${lessonId}/blocks/${blockId}`);
}

export function startAttempt(token) {
  return request(`/${encodeURIComponent(token)}/start`, { method: "POST", body: "{}" });
}

export function startLessonHomework(lessonId, blockId) {
  return request(`/lesson-homework/${lessonId}/blocks/${blockId}/start`, {
    method: "POST",
    body: "{}",
  });
}

export function fetchAttempt(attemptId) {
  return request(`/attempts/${attemptId}`);
}

export function saveAnswer(attemptId, problemIdNo, answer) {
  return request(`/attempts/${attemptId}/answers`, {
    method: "PUT",
    body: JSON.stringify({ problem_id_no: problemIdNo, answer }),
  });
}

export function runCode(attemptId, payload) {
  return request(`/attempts/${attemptId}/code`, { method: "POST", body: JSON.stringify(payload) });
}

/**
 * 历史作答的分页列表。候考页本身只带最近 5 条 + 摘要，「查看全部」走这里。
 *
 * 为什么不让候考页一次给全：它是每次进入都要拉的接口，而不限次数的练习卷记录会一直涨。
 */
export function fetchAttemptHistory(token, { page = 1, size = 20 } = {}) {
  return fetchAttemptHistoryAt(`/${encodeURIComponent(token)}/attempts`, { page, size });
}

export function fetchLessonHomeworkHistory(lessonId, blockId, { page = 1, size = 20 } = {}) {
  return fetchAttemptHistoryAt(`/lesson-homework/${lessonId}/blocks/${blockId}/attempts`, {
    page,
    size,
  });
}

function fetchAttemptHistoryAt(path, { page, size }) {
  const query = new URLSearchParams({ page: String(page), size: String(size) });
  return request(`${path}?${query}`);
}

/** 某道编程题的提交记录。只含 kind="submit"，逐点结果按 feedback_mode 裁剪，带自己的 code。 */
export function fetchSubmissions(attemptId, problemIdNo, { page = 1, size = 20 } = {}) {
  const query = new URLSearchParams({
    problem_id_no: problemIdNo,
    page: String(page),
    size: String(size),
  });
  return request(`/attempts/${attemptId}/submissions?${query}`);
}

/** 单条提交的判题进度。payload.done 为真才是终态，前端据此停止轮询。 */
export function fetchSubmission(attemptId, submissionId) {
  return request(`/attempts/${attemptId}/submissions/${submissionId}`);
}

/**
 * 提交并轮询到判题终态。
 *
 * 判题是异步的：runCode 只落一条 queued 就返回，结果得自己轮。250ms 一次是权衡后的
 * 值——空载判题 0.5 秒左右，再密只是空转；再稀就能被人感觉出卡顿。
 *
 * onProgress 每轮回调一次（带 queue_position），调用方拿它显示「排队中 第 N 位」。
 * signal 用来在切题/组件卸载时掐断轮询，否则学员切走之后这个循环还在打接口。
 */
export async function runCodeAndWait(attemptId, payload, { onProgress, signal } = {}) {
  const queued = await runCode(attemptId, payload);
  onProgress?.(queued);
  if (queued.done) return queued;

  const interval = 250;
  // 判题真挂了也不能永远转下去——后端 10 分钟才清僵尸，前端等不了那么久。
  const deadline = Date.now() + 120_000;
  for (;;) {
    if (signal?.aborted) throw new ExamError("已取消。", 0);
    await new Promise((resolve) => setTimeout(resolve, interval));
    if (signal?.aborted) throw new ExamError("已取消。", 0);
    const current = await fetchSubmission(attemptId, queued.id);
    onProgress?.(current);
    if (current.done) return current;
    if (Date.now() > deadline)
      throw new ExamError("判题超时未返回结果，请稍后在「提交记录」里查看。", 0);
  }
}

export function submitAttempt(attemptId) {
  return request(`/attempts/${attemptId}/submit`, { method: "POST", body: "{}" });
}

export function fetchResult(attemptId) {
  return request(`/attempts/${attemptId}/result`);
}

/** 这张卷的排行榜。成绩未公开时服务端回 403，调用方据此直接不渲染，不算错误。 */
export function fetchLeaderboard(attemptId) {
  return request(`/attempts/${attemptId}/leaderboard`);
}

// 判题终态 → 中文文案。后端 app/judge/base.py 新增状态时这里必须同步。
export const JUDGE_STATUS_TEXT = {
  accepted: "全部通过",
  wrong_answer: "答案错误",
  compile_error: "编译错误",
  runtime_error: "运行错误",
  time_limit: "超出时间限制",
  memory_limit: "超出内存限制",
  judge_failed: "判题异常",
};

export const QUESTION_TYPE_TEXT = {
  choice: "单选题",
  multi_choice: "多选题",
  judge: "判断题",
  fill: "填空题",
  programming: "编程题",
};
