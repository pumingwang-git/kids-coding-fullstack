/**
 * 同域 API 客户端。
 * - 认证沿用主站 Cookie（credentials: 'include'）
 * - 写请求携带 X-CSRF-Token，**令牌按目标端点选**（见下）
 * - 错误规范化为 {status, code, message}
 */

function getCookie (name) {
    const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
}

/**
 * 后端有两套**互不通用**的 CSRF 令牌，各自校验各自的 Cookie：
 *
 * | 端点 | Cookie | 签发 | 校验实现 |
 * | --- | --- | --- | --- |
 * | `/api/scratch/...` | `csrf_token` | `GET /api/auth/csrf` | `auth_secure.require_csrf` |
 * | `/api/admin/...` | `admin_csrf_token` | `GET /api/admin/csrf` | `admin_auth.require_csrf` |
 *
 * Studio 一个页面同时用到两边（学生保存/提交走前者，教研录制走后者），所以令牌
 * **必须按 URL 选**，不能整个客户端固定用一种。
 *
 * 这里踩过一次：早先所有写请求一律取 `admin_csrf_token`，学生保存于是把管理端
 * 令牌发给学生端接口，`require_csrf` 比对失败 → 403「CSRF 校验失败。」。而且
 * `GET /api/admin/csrf` 不校验管理员身份，学生也能拿到令牌，所以这条路是**必然**
 * 失败而不是偶发——只是在「打开编程工作台」跳首页的问题修好之前一直没走到。
 */
const CSRF_SCOPES = {
    student: {
        cookie: 'csrf_token',
        mint: '/api/auth/csrf',
        missing: '未获取到 CSRF 令牌，请重新登录后再试。'
    },
    admin: {
        cookie: 'admin_csrf_token',
        mint: '/api/admin/csrf',
        missing: '未获取到管理端 CSRF 令牌，请重新登录后台后再试。'
    }
};

function csrfScope (url) {
    return String(url).startsWith('/api/admin/') ? CSRF_SCOPES.admin : CSRF_SCOPES.student;
}

async function csrfToken (scope, forceRefresh = false) {
    // Studio 可能是独立开发服务（8602），不能假设用户刚好先在本站点写过一次请求，
    // 所以没有 Cookie 时主动让后端签发一个。端口不同不影响 localhost Cookie，
    // /api 代理会把请求送到同一后端。
    const existing = !forceRefresh && getCookie(scope.cookie);
    if (existing) return existing;
    const response = await fetch(scope.mint, {credentials: 'include'});
    if (!response.ok) throw await toError(response);
    const token = getCookie(scope.cookie);
    if (!token) throw new Error(scope.missing);
    return token;
}

/** 把非 2xx 响应规范化为统一错误对象 */
/**
 * 把 FastAPI 的 `detail` 变成一句人话。
 *
 * `detail` 有三种形状：字符串（我们自己 raise 的业务文案）、对象、以及**校验错误的
 * 数组**（422 的默认形状）。原先直接塞给 `new Error(detail)`，后两种会被 JS 拼成
 * 字符串 `[object Object]` —— 学生看到的就是"保存失败：[object Object]"，等于没提示。
 */
function detailToMessage (detail) {
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        const parts = detail
            .map(item => {
                if (typeof item === 'string') return item;
                if (!item || typeof item !== 'object') return null;
                const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : null;
                return [field, item.msg].filter(Boolean).join('：') || null;
            })
            .filter(Boolean);
        return parts.length ? parts.join('；') : null;
    }
    if (detail && typeof detail === 'object') {
        return detail.message || detail.msg || null;
    }
    return null;
}

async function toError (response) {
    let detail = null;
    try {
        detail = await response.json();
    } catch (e) {
        detail = null;
    }
    const err = new Error(
        (detail && detailToMessage(detail.detail)) || `请求失败（HTTP ${response.status}）`
    );
    err.status = response.status;
    err.code = detail && detail.code;
    err.detail = detail;
    return err;
}

function send (url, options, token) {
    // 字符串 body 必须自报 application/json。不写的话浏览器给 fetch 兜的是
    // `text/plain;charset=UTF-8`，FastAPI 解不出请求体，**所有 JSON 写请求一律 422**
    // ——`createWork` / `updateWork` / `deleteWork` / `shareWork` 全在这条路上。
    // FormData（保存 .sb3）不能碰：它要自己带 multipart 边界。
    const isJsonBody = typeof options.body === 'string';
    return fetch(url, {
        credentials: 'include',
        ...options,
        headers: {
            ...(token ? {'X-CSRF-Token': token} : {}),
            ...(isJsonBody ? {'Content-Type': 'application/json'} : {}),
            ...(options.headers || {})
        }
    });
}

async function request (url, options = {}) {
    const writing = !['GET', 'HEAD'].includes(String(options.method || 'GET').toUpperCase());
    const scope = writing ? csrfScope(url) : null;
    let response = await send(url, options, scope ? await csrfToken(scope) : null);

    // CSRF Cookie 随会话轮换，而 Studio 是长时间开着的页面（一节课能编四十分钟）。
    // 令牌过期时重取一次再试，而不是把「保存失败」直接甩给学生——学员端的 exam.js
    // 出于同一个理由做了同样的事。只重试这一种 403：其它 403 是真的没权限。
    if (writing && response.status === 403) {
        const stale = await response.clone().json().catch(() => null);
        if (stale && stale.detail === 'CSRF 校验失败。') {
            response = await send(url, options, await csrfToken(scope, true));
        }
    }

    if (!response.ok) {
        throw await toError(response);
    }
    if (response.status === 204) return null;
    return response.json();
}

// ---- 学生端 6 个端点 ----

/** GET /api/scratch/lesson-blocks/{block_id} */
export function fetchLessonBlockContext (blockId) {
    return request(`/api/scratch/lesson-blocks/${blockId}`);
}

/** GET /api/scratch/lesson-blocks/{block_id}/starter.sb3 -> ArrayBuffer */
export async function fetchStarterSb3 (blockId) {
    const response = await fetch(`/api/scratch/lesson-blocks/${blockId}/starter.sb3`, {
        credentials: 'include'
    });
    if (!response.ok) throw await toError(response);
    return response.arrayBuffer();
}

/**
 * GET /api/scratch/lesson-blocks/{block_id}/demo.sb3 -> ArrayBuffer
 *
 * 与管理端的 `fetchChallengeSb3` 分开：那条走 `/api/admin/...`，门是教研权限；这条
 * 走学生课时门控 + 一次终态提交。合成一个"取 .sb3"的通用函数就等于把两套授权
 * 混在一个调用点上。
 */
export async function fetchDemoSb3 (blockId) {
    const response = await fetch(`/api/scratch/lesson-blocks/${blockId}/demo.sb3`, {
        credentials: 'include'
    });
    if (!response.ok) throw await toError(response);
    return response.arrayBuffer();
}

/** GET /api/scratch/projects/{project_id}/content.sb3 -> ArrayBuffer */
export async function fetchProjectContentSb3 (projectId) {
    const response = await fetch(`/api/scratch/projects/${projectId}/content.sb3`, {
        credentials: 'include'
    });
    if (!response.ok) throw await toError(response);
    return response.arrayBuffer();
}

/**
 * PUT /api/scratch/projects/{project_id}
 * @param {number} projectId
 * @param {Blob} sb3Blob  vm.saveProjectSb3() 的产物
 * @param {'autosave'|'manual'} source
 * @param {number} [challengeId]
 */
export function saveProjectSb3 (projectId, sb3Blob, source, challengeId) {
    const form = new FormData();
    form.append('file', sb3Blob, 'project.sb3');
    form.append('source', source);
    if (challengeId != null) form.append('challenge_id', String(challengeId));
    return request(`/api/scratch/projects/${projectId}`, {
        method: 'PUT',
        body: form
    });
}

/** POST /api/scratch/lesson-blocks/{block_id}/submit（无请求体） */
export function submitProject (blockId) {
    return request(`/api/scratch/lesson-blocks/${blockId}/submit`, {
        method: 'POST'
    });
}

/** GET /api/scratch/lesson-blocks/{block_id}/submissions */
export function fetchSubmissions (blockId) {
    return request(`/api/scratch/lesson-blocks/${blockId}/submissions`);
}

// ---- 管理端：教研在 Studio 里编写初始项目（21b 补充实施记录 2026-08-14） ----
//
// 刻意与学生端三个端点分开：教研预览**绝不能**产生一条学生作品或提交记录，
// 两套调用不共用函数，就不存在"传错 id 把老师的试做写进学生项目"这类事故。

/** GET /api/admin/scratch/challenges/{id}/studio-context */
export function fetchAdminStudioContext (challengeId) {
    return request(`/api/admin/scratch/challenges/${challengeId}/studio-context`);
}

/**
 * GET /api/admin/scratch/challenges/{id}/{starter|demo}.sb3 -> ArrayBuffer
 * @param {string} url 直接用服务端下发的 `starter_url` / `demo_url`，不在前端拼路径
 */
export async function fetchChallengeSb3 (url) {
    const response = await fetch(url, {credentials: 'include'});
    if (!response.ok) throw await toError(response);
    return response.arrayBuffer();
}

// ---- 管理端：教师批改台只读装载提交快照（文档 23 §7.3） ----
//
// 与 admin_preview（按 challenge_id 装「挑战当前初始项目」）刻意分开：这里按
// submission_id 装「学生提交时冻结的那一版」，两个证据对不上就是批改事故。

/** GET /api/admin/scratch/submissions/{id}（返回 snapshot.download_url 等） */
export function fetchAdminReviewContext (submissionId) {
    return request(`/api/admin/scratch/submissions/${submissionId}`);
}

/** GET 提交快照的 .sb3 -> ArrayBuffer（url 用服务端下发的 snapshot.download_url） */
export async function fetchSubmissionSb3 (url) {
    const response = await fetch(url, {credentials: 'include'});
    if (!response.ok) throw await toError(response);
    return response.arrayBuffer();
}

/**
 * POST /api/admin/scratch/challenges/{id}/{starter|demo}-project
 * 与学生端保存同一个 multipart 形状（字段名 `file`）。
 * @param {string} url 服务端下发的 `starter_write_url` / `demo_write_url`；null 表示不允许写
 * @param {Blob} sb3Blob vm.saveProjectSb3() 的产物
 * @param {string} [filename] 落在 multipart 里的文件名。后端不读它，但审计日志和
 *   排查时它是唯一能区分"这次传的是初始项目还是示范项目"的线索，所以由调用方给。
 */
export function uploadChallengeProject (url, sb3Blob, filename = 'project.sb3') {
    const form = new FormData();
    form.append('file', sb3Blob, filename);
    return request(url, {method: 'POST', body: form});
}

// ---- 自由作品与作品广场（scratch_works.py，2026-08-14） ----
//
// 自由作品是"创作"本身：一人多份、可命名、可公开，公开作品进广场展出。
// 与闯关（上面那一组）刻意分开：闯关有提交判定和版本冻结，自由作品只有当前版本。

/** POST /api/scratch/works —— 新建空白自由作品；公开状态随创建原子写入。 */
export function createWork (title, isPublic = false) {
    return request('/api/scratch/works', {
        method: 'POST',
        body: JSON.stringify({title: title || '未命名作品', is_public: isPublic})
    });
}

/** GET /api/scratch/works —— 我的作品列表 */
export function fetchMyWorks () {
    return request('/api/scratch/works');
}

/** GET /api/scratch/works/{id} —— 编辑上下文（title / content_url / limits） */
export function fetchWorkContext (workId) {
    return request(`/api/scratch/works/${workId}`);
}

/** PUT /api/scratch/works/{id} —— 保存自由作品当前版本（multipart file） */
export function saveWorkSb3 (workId, sb3Blob, source = 'autosave') {
    const form = new FormData();
    form.append('file', sb3Blob, 'work.sb3');
    form.append('source', source);
    return request(`/api/scratch/works/${workId}`, {method: 'PUT', body: form});
}

/** GET /api/scratch/works/{id}/content.sb3 -> ArrayBuffer */
export async function fetchWorkContentSb3 (workId) {
    const response = await fetch(`/api/scratch/works/${workId}/content.sb3`, {
        credentials: 'include'
    });
    if (!response.ok) throw await toError(response);
    return response.arrayBuffer();
}

/** PATCH /api/scratch/works/{id} —— 更新标题/简介/公开开关 */
export function updateWork (workId, patch) {
    return request(`/api/scratch/works/${workId}`, {
        method: 'PATCH',
        body: JSON.stringify(patch)
    });
}

/** DELETE /api/scratch/works/{id} */
export function deleteWork (workId) {
    return request(`/api/scratch/works/${workId}`, {method: 'DELETE'});
}

/** POST /api/scratch/works/share —— 把闯关工作副本发布为广场作品（幂等） */
export function shareWork (projectId) {
    return request('/api/scratch/works/share', {
        method: 'POST',
        body: JSON.stringify({project_id: projectId})
    });
}

/** GET /api/scratch/gallery —— 公开作品分页（?page=&size=&sort=&keyword=） */
export function fetchGallery (params = {}) {
    const query = new URLSearchParams(params).toString();
    return request(`/api/scratch/gallery${query ? `?${query}` : ''}`);
}

/** GET /api/scratch/gallery/{id} —— 公开作品详情（views+1） */
export function fetchGalleryWork (workId) {
    return request(`/api/scratch/gallery/${workId}`);
}

/** GET /api/scratch/gallery/{id}/content.sb3 -> ArrayBuffer（公开作品预览装载） */
export async function fetchGalleryContentSb3 (workId) {
    const response = await fetch(`/api/scratch/gallery/${workId}/content.sb3`, {
        credentials: 'include'
    });
    if (!response.ok) throw await toError(response);
    return response.arrayBuffer();
}

export {getCookie};
