// Scratch 管理端 API 封装：真实契约 + 契约 mock。
//
// 后端 Scratch 接口（开发文档 21 §5.3）尚未交付，本模块做两件事：
//   1. 定义管理端依赖的最小契约（路径、字段、错误形态），页面代码只调这里；
//   2. 提供 localStorage 契约 mock：URL 加 ?scratch_mock=1 开启（会话内保持），
//      ?scratch_mock=0 关闭。mock 不绕过权限写数据库，只是在浏览器里模拟契约响应。
//
// 验收用开关（仅 mock 模式生效，模拟失败时前端绝不显示成功 Toast）：
//   ?scratch_mock_fail=1  所有 Scratch 请求报 500 —— 模拟 API 失败 / 项目上传失败
//   挑战保存携带 base_version，与服务端 edit_seq 不一致报 409 —— 模拟保存冲突
//
// 课时内容块端点（/lessons/{id}/blocks 等）已存在但尚不认识 scratch 块类型：
// mock 模式下由本模块接管 scratch 块的存取（mock 块 id 为 ≤ -1001 的负数，永不与真实 id 冲突），
// 其余块类型与排序原样透传真实后端。

import { adminRequest } from "./admin-api.js";
import { publishChecks } from "./admin-scratch-core.js";

const MOCK_FLAG = "scratch_mock";
const FAIL_FLAG = "scratch_mock_fail";
const DB_KEY = "scratch_mock_db_v1";
const MOCK_ID_BASE = -1001;

// ==================== mock 开关 ====================

// URL 参数优先（可分享链接直接进 mock 演示），随后粘到 sessionStorage。
function syncFlagsFromUrl() {
  const params = new URLSearchParams(location.search);
  if (params.get(MOCK_FLAG) === "1") sessionStorage.setItem(MOCK_FLAG, "1");
  if (params.get(MOCK_FLAG) === "0") sessionStorage.removeItem(MOCK_FLAG);
  if (params.get(FAIL_FLAG) === "1") sessionStorage.setItem(FAIL_FLAG, "1");
  if (params.get(FAIL_FLAG) === "0") sessionStorage.removeItem(FAIL_FLAG);
}

export function scratchMockEnabled() {
  syncFlagsFromUrl();
  return sessionStorage.getItem(MOCK_FLAG) === "1";
}

export function setScratchMock(on) {
  if (on) sessionStorage.setItem(MOCK_FLAG, "1");
  else sessionStorage.removeItem(MOCK_FLAG);
}

function mockFailing() {
  syncFlagsFromUrl();
  return sessionStorage.getItem(FAIL_FLAG) === "1";
}

export function setScratchMockFail(on) {
  if (on) sessionStorage.setItem(FAIL_FLAG, "1");
  else sessionStorage.removeItem(FAIL_FLAG);
}

// ==================== mock 数据 ====================

function seedDb() {
  const now = new Date().toISOString();
  return {
    nextChallengeId: 3,
    nextBlockSeq: 0,
    challenges: [
      {
        id: 1,
        title: "第一课：小猫打招呼",
        instructions_md: "点击绿旗后，让小猫移动 10 步并说出「你好」。",
        starter_project: { name: "starter-cat.sb3", size: 42137, uploaded_at: now },
        demo_project: { name: "demo-cat.sb3", size: 45301, uploaded_at: now },
        analysis_video_id: null,
        allowed_extensions: [],
        hints: ["先在「事件」里找到「当绿旗被点击」。", "「说」积木在「外观」分类里。"],
        rules_json: [
          { type: "require_after_hat", hat: "event_whenflagclicked", opcode: "motion_movesteps" },
          { type: "require_opcode", opcode: "motion_movesteps" },
          { type: "require_say_text", text: "你好" },
        ],
        status: "published",
        version: 2,
        edit_seq: 2,
        updated_at: now,
      },
      {
        id: 2,
        title: "接苹果游戏（草稿）",
        instructions_md: "",
        starter_project: null,
        demo_project: null,
        analysis_video_id: null,
        allowed_extensions: ["pen"],
        hints: [],
        rules_json: [],
        status: "draft",
        version: 1,
        edit_seq: 1,
        updated_at: now,
      },
    ],
    submissions: [
      {
        id: 1,
        student_id: 101,
        student_name: "张小明",
        challenge_id: 1,
        submitted_at: now,
        status: "passed",
        attempt_count: 3,
        snapshot: { revision_no: 5, saved_at: now, content_hash: "sha256:9f2c…a1", size_bytes: 51204 },
        evaluation: { rules_passed: 3, rules_total: 3 },
        feedback: "全部规则通过。",
      },
      {
        id: 2,
        student_id: 102,
        student_name: "李雨桐",
        challenge_id: 1,
        submitted_at: now,
        status: "failed",
        attempt_count: 1,
        snapshot: { revision_no: 2, saved_at: now, content_hash: "sha256:71be…c4", size_bytes: 48890 },
        evaluation: { rules_passed: 2, rules_total: 3, missing: ["require_say_text"] },
        feedback: "还没有让小猫说出指定文本，检查「说」积木。",
      },
      {
        id: 3,
        student_id: 103,
        student_name: "王一凡",
        challenge_id: 1,
        submitted_at: now,
        status: "evaluating",
        attempt_count: 2,
        snapshot: { revision_no: 4, saved_at: now, content_hash: "sha256:0d77…e9", size_bytes: 50112 },
        evaluation: null,
        feedback: null,
      },
    ],
    // { [lessonId]: [scratchBlock...] } —— 只存 scratch 块，其余块仍走真实后端
    blocks: {},
  };
}

function loadDb() {
  try {
    const raw = localStorage.getItem(DB_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* 损坏则重建 */
  }
  const db = seedDb();
  localStorage.setItem(DB_KEY, JSON.stringify(db));
  return db;
}

function saveDb(db) {
  localStorage.setItem(DB_KEY, JSON.stringify(db));
}

// mock 对外严格镜像真实管理端契约；旧 localStorage 数据仍可读，但不再泄漏旧字段名。
function serializeChallenge(db, challenge) {
  const rules = challenge.rules || challenge.rules_json || [];
  return {
    id: challenge.id,
    title: challenge.title,
    instructions_md: challenge.instructions_md || "",
    status: challenge.status,
    version: challenge.version,
    edit_seq: challenge.edit_seq ?? challenge.version,
    allowed_extensions: challenge.allowed_extensions || [],
    hints: challenge.hints || [],
    rules,
    has_starter: Boolean(challenge.starter_project),
    has_demo: Boolean(challenge.demo_project),
    analysis_video_id: challenge.analysis_video_id || null,
    has_analysis_video: Boolean(challenge.analysis_video_id),
    starter_size_bytes: challenge.starter_project?.size || 0,
    bound_block_count: Object.values(db.blocks).flat().filter((block) => block.scratch?.challenge_id === challenge.id).length,
    submission_count: db.submissions.filter((submission) => submission.challenge_id === challenge.id).length,
    // 审核人/打回记录（对齐真实后端 _serialize 的字段形状）
    reviewed_by: challenge.reviewed_by || null,
    reviewed_at: challenge.reviewed_at || null,
    rejection: challenge.rejection_reason
      ? { by: challenge.rejected_by || null, at: challenge.rejected_at || null, reason: challenge.rejection_reason }
      : null,
    updated_at: challenge.updated_at,
  };
}

function fail500() {
  throw new Error("模拟 API 失败：服务器返回 500（scratch_mock_fail=1 测试开关）。");
}

// 用挑战当前状态回填块上的展示快照（发布后解绑、撤回挑战都会反映成「待配置」）。
function hydrateBlock(db, block) {
  const challenge = db.challenges.find((c) => c.id === block.scratch?.challenge_id);
  return {
    ...block,
    scratch: {
      challenge_id: block.scratch?.challenge_id ?? null,
      challenge_title: challenge?.title || null,
      challenge_status: challenge?.status || null,
    },
  };
}

// ==================== mock 路由 ====================

async function mockRequest(path, options = {}) {
  // 模拟网络延迟，加载/失败状态在验收里才看得见
  await new Promise((resolve) => setTimeout(resolve, 120));
  if (mockFailing()) fail500();

  const db = loadDb();
  const method = options.method || "GET";
  const body = options.body ? JSON.parse(options.body) : {};
  const [pathname, queryString] = path.split("?");
  const params = new URLSearchParams(queryString || "");
  const seg = pathname.split("/").filter(Boolean); // ["scratch", "challenges", "1", ...]

  const now = () => new Date().toISOString();
  const notFound = () => {
    throw new Error("资源不存在或已被删除。");
  };

  // ---- 挑战 ----
  if (seg[0] === "scratch" && seg[1] === "challenges") {
    if (seg.length === 2 && method === "GET") {
      let items = db.challenges.map((c) => serializeChallenge(db, c));
      const status = params.get("status");
      const keyword = params.get("keyword")?.trim();
      if (status) items = items.filter((c) => c.status === status);
      if (keyword) items = items.filter((c) => c.title.includes(keyword) || String(c.id) === keyword);
      const sorted = items.sort((a, b) => b.id - a.id);
      return { total: sorted.length, page: 1, size: sorted.length || 20, items: sorted };
    }
    if (seg.length === 2 && method === "POST") {
      const title = String(body.title || "").trim();
      if (!title) throw new Error("请填写挑战标题。");
      const challenge = {
        id: db.nextChallengeId++,
        title,
        instructions_md: "",
        starter_project: null,
        demo_project: null,
        analysis_video_id: null,
        allowed_extensions: [],
        hints: [],
        rules: [],
        status: "draft",
        version: 1,
        edit_seq: 1,
        updated_at: now(),
      };
      db.challenges.push(challenge);
      saveDb(db);
      return serializeChallenge(db, challenge);
    }
    if (seg[2] === "options" && method === "GET") {
      // 绑定下拉用：全部挑战 + 状态（未发布的要标出，防止误以为配好了）
      return { items: db.challenges.map((c) => ({ id: c.id, title: c.title, status: c.status, version: c.version })) };
    }
    const id = Number(seg[2]);
    const challenge = db.challenges.find((c) => c.id === id);
    if (!challenge) notFound();
    if (seg.length === 3 && method === "GET") return serializeChallenge(db, challenge);
    if (seg.length === 3 && method === "PUT") {
      if (challenge.status !== "draft") throw new Error("只有草稿挑战可以编辑；已发布挑战请先点「修改」撤回为草稿。");
      // 与真实后端同口径：base_version 比对编辑序号 edit_seq，不是发布版次 version。
      if (Number(body.base_version) !== challenge.edit_seq) {
        throw new Error("保存冲突：该挑战刚被其他人修改，请刷新后基于最新版本重试。");
      }
      Object.assign(challenge, {
        title: body.title,
        instructions_md: body.instructions_md ?? "",
        analysis_video_id: Number(body.analysis_video_id) || null,
        allowed_extensions: body.allowed_extensions || [],
        hints: body.hints || [],
        rules: body.rules || [],
        // 只 bump edit_seq：version 是发布版次，草稿编辑不动它。
        edit_seq: (challenge.edit_seq || 0) + 1,
        updated_at: now(),
      });
      saveDb(db);
      return serializeChallenge(db, challenge);
    }
    if (seg[3] === "duplicate" && method === "POST") {
      const suffix = "（新版本）";
      const copied = {
        ...challenge,
        id: db.nextChallengeId++,
        title: `${String(challenge.title).slice(0, 200 - suffix.length)}${suffix}`,
        status: "draft",
        version: 1,
        edit_seq: 1,
        updated_at: now(),
      };
      db.challenges.push(copied);
      saveDb(db);
      return serializeChallenge(db, copied);
    }
    if (seg[3] === "publish" && method === "POST") {
      const missing = publishChecks(serializeChallenge(db, challenge));
      if (missing.length) {
        throw new Error(`挑战还不完整，不能发布：${missing.join("、")}。`);
      }
      challenge.status = "published";
      // version = 第几次发布：首次发布保持 1，撤回时才 +1（与真实后端同口径）。
      challenge.updated_at = now();
      saveDb(db);
      return { challenge: serializeChallenge(db, challenge), warnings: [] };
    }
    if (seg[3] === "submit" && method === "POST") {
      const missing = publishChecks(serializeChallenge(db, challenge));
      if (missing.length) throw new Error(`挑战还不完整，不能提交审核：${missing.join("、")}。`);
      challenge.status = "pending"; challenge.updated_at = now(); saveDb(db);
      return serializeChallenge(db, challenge);
    }
    if (seg[3] === "approve" && method === "POST") {
      if (challenge.status !== "pending") throw new Error("只有待审核挑战可以通过。");
      challenge.status = "published";
      challenge.reviewed_by = { id: 1, display_name: "当前管理员" };
      challenge.reviewed_at = now();
      challenge.updated_at = now();
      saveDb(db);
      return { challenge: serializeChallenge(db, challenge), warnings: [] };
    }
    if (seg[3] === "reject" && method === "POST") {
      if (challenge.status !== "pending") throw new Error("只有待审核挑战可以打回。");
      const reason = String(body?.reason || "").trim();
      if (!reason) throw new Error("请填写打回原因。");
      challenge.status = "draft";
      challenge.rejected_by = { id: 1, display_name: "当前管理员" };
      challenge.rejected_at = now();
      challenge.rejection_reason = reason;
      challenge.updated_at = now();
      saveDb(db);
      return serializeChallenge(db, challenge);
    }
    if ((seg[3] === "withdraw" || seg[3] === "unpublish") && method === "POST") {
      // unpublish 是真实契约端点；withdraw 是 21c 早期管理端用的别名，两者都收。
      if (challenge.status !== "published") return serializeChallenge(db, challenge);
      challenge.status = "draft";
      challenge.version += 1; // 撤回再发就是新的一版
      challenge.updated_at = now();
      saveDb(db);
      return serializeChallenge(db, challenge);
    }
    if (seg.length === 3 && method === "DELETE") {
      // 与真实后端同口径：draft / published 可删，pending 不可删（审核中不能删）；
      // 被课时块绑定 / 已有学生提交的挑战 409（引用保护）。
      if (challenge.status === "pending") throw new Error("待审核的挑战不能删除，请先打回。");
      const bound = Object.values(db.blocks).flat().filter((block) => block.scratch?.challenge_id === challenge.id).length;
      const submissions = db.submissions.filter((submission) => submission.challenge_id === challenge.id).length;
      if (bound || submissions) throw new Error("已绑定课时或已有学生提交的挑战不能删除。");
      db.challenges = db.challenges.filter((item) => item.id !== challenge.id); saveDb(db);
      return null;
    }
    if ((seg[3] === "starter-project" || seg[3] === "demo-project") && method === "POST") {
      // mock 上传：只记录文件名/大小；非 .sb3 直接拒（契约：后端会校验 ZIP/Scratch 结构）
      const name = String(body.file_name || "");
      if (!name.toLowerCase().endsWith(".sb3")) throw new Error("项目上传失败：只接受 .sb3 项目文件。");
      if (Number(body.size) > 10 * 1024 * 1024) throw new Error("项目上传失败：文件超过 10MB 上限。");
      challenge[seg[3] === "starter-project" ? "starter_project" : "demo_project"] = {
        name,
        size: Number(body.size) || 0,
        uploaded_at: now(),
      };
      challenge.updated_at = now();
      saveDb(db);
      return serializeChallenge(db, challenge);
    }
  }

  // ---- 学生作品（只读） ----
  if (seg[0] === "scratch" && seg[1] === "submissions") {
    if (seg.length === 2 && method === "GET") {
      let items = db.submissions.map((s) => {
        const challenge = db.challenges.find((c) => c.id === s.challenge_id);
        return { ...s, challenge_title: challenge?.title || `#${s.challenge_id}`, snapshot: undefined, evaluation: undefined, feedback: undefined };
      });
      const challengeId = params.get("challenge_id");
      if (challengeId) items = items.filter((s) => s.challenge_id === Number(challengeId));
      const status = params.get("status");
      if (status) items = items.filter((s) => s.status === status);
      const page = Number(params.get("page")) || 1;
      const size = Number(params.get("page_size")) || 20;
      return { total: items.length, items: items.slice((page - 1) * size, page * size) };
    }
    const id = Number(seg[2]);
    const submission = db.submissions.find((s) => s.id === id);
    if (!submission) notFound();
    if (seg.length === 3 && method === "GET") {
      const challenge = db.challenges.find((c) => c.id === submission.challenge_id);
      return { ...submission, challenge_title: challenge?.title || `#${submission.challenge_id}` };
    }
  }

  // ---- 课时内容块里的 scratch 块 ----
  const blocksMatch = /^\/lessons\/(\d+)\/blocks(\/reorder)?$/.exec(pathname);
  if (blocksMatch) {
    const lessonId = Number(blocksMatch[1]);
    const mockBlocks = db.blocks[lessonId] || [];
    if (method === "GET" && !blocksMatch[2]) {
      // 合并真实块 + mock scratch 块；真实后端不可用时只给 mock 块（纯离线演示）
      let base = { lesson: { id: lessonId, title: `课时 #${lessonId}（mock 演示）`, duration_minutes: 0 }, blocks: [] };
      try {
        base = await adminRequest(pathname);
      } catch {
        /* 离线演示：真实块拉不到不挡路 */
      }
      const merged = [...(base.blocks || []), ...mockBlocks.map((b) => hydrateBlock(db, b))].map((b, i) => ({ ...b, sort_order: i }));
      return { lesson: base.lesson, blocks: merged };
    }
    if (method === "POST" && !blocksMatch[2] && body.block_type === "scratch") {
      const block = {
        id: MOCK_ID_BASE - db.nextBlockSeq++,
        lesson_id: lessonId,
        block_type: "scratch",
        title: body.title,
        required: body.required !== false,
        unlock_rule: body.unlock_rule || "free",
        sort_order: mockBlocks.length,
        scratch: { challenge_id: body.detail?.scratch?.challenge_id ?? null },
      };
      mockBlocks.push(block);
      db.blocks[lessonId] = mockBlocks;
      saveDb(db);
      return hydrateBlock(db, block);
    }
    if (method === "POST" && blocksMatch[2]) {
      // 排序：mock 块按 orderedIds 中的相对位置重排；若不含 mock id 则透传真实后端
      const ids = body.ids || [];
      if (!ids.some((id) => mockBlocks.some((b) => b.id === Number(id)))) {
        return adminRequest(path, options);
      }
      const ordered = ids.map((id) => mockBlocks.find((b) => b.id === Number(id))).filter(Boolean);
      db.blocks[lessonId] = ordered;
      saveDb(db);
      return { ok: true };
    }
  }
  const blockMatch = /^\/lesson-blocks\/(-?\d+)$/.exec(pathname);
  if (blockMatch) {
    const id = Number(blockMatch[1]);
    for (const lessonId of Object.keys(db.blocks)) {
      const index = db.blocks[lessonId].findIndex((b) => b.id === id);
      if (index === -1) continue;
      if (method === "PUT") {
        const block = db.blocks[lessonId][index];
        Object.assign(block, {
          title: body.title ?? block.title,
          required: body.required !== false,
          unlock_rule: body.unlock_rule || "free",
          scratch: { challenge_id: body.detail?.scratch?.challenge_id ?? block.scratch.challenge_id },
        });
        saveDb(db);
        return hydrateBlock(db, block);
      }
      if (method === "DELETE") {
        db.blocks[lessonId].splice(index, 1);
        saveDb(db);
        return null;
      }
    }
    // 非 mock 块：透传真实后端
    return adminRequest(path, options);
  }

  throw new Error(`mock 未覆盖的契约路径：${method} ${pathname}`);
}

// ==================== 对外接口 ====================

// Scratch 专属端点：mock 开启时走 mock，否则走真实后端契约。
export async function scratchRequest(path, options = {}) {
  if (scratchMockEnabled()) return mockRequest(path, options);
  return adminRequest(path, options);
}

// 课时内容块端点：仅 mock 模式且命中 scratch 块时接管，其余一律透传。
export async function blocksRequest(path, options = {}) {
  if (scratchMockEnabled()) return mockRequest(path, options);
  return adminRequest(path, options);
}
