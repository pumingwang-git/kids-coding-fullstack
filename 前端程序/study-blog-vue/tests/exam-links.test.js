// @vitest-environment jsdom
// exam-links.js 页面级护栏（jsdom + 真实挂载 exam-links.html 的 body）。
// 覆盖《4、后台考试链接-管理模块》10.2：徽章优先级、allowed_actions 驱动按钮、
// 复制三件套、删除确认 + If-Match、学员体验预览、模式联动、预设填充、提醒规则前端预检。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const PAGE_HTML = resolve(process.cwd(), "public/admin/exam-links.html");

const PAPERS = [
  { id: 7, paper_id_no: "P000007", title: "三班期中卷", paper_type: "测试卷", subject: "cpp", status: "published" },
  { id: 8, paper_id_no: "P000008", title: "期末模拟卷", paper_type: "模拟卷", subject: "cpp", status: "published" },
];

const LINK_BASE = {
  id: 12, paper_id: 7, name: "三班期中考", status: "active", phase: "running",
  exam_url: "/exam/3f9a1c", revision: 3,
  open_at: "2026-06-10T06:00:00", close_at: "2026-06-10T08:00:00",
  duration_minutes: 90, late_start_policy: "truncate", attempt_limit: 1, score_policy: "best",
  penalty_minutes: 0, feedback_mode: "realtime", show_analysis: "after_submit", show_score: "immediate",
  shuffle_questions: true, shuffle_options: false,
  notice: "", notice_ack_required: false, entry_open_minutes: 15, remind_minutes: "30,10,5", warn_unanswered: true,
  paper: PAPERS[0], owner: { id: 1, display_name: "root" },
  allowed_actions: ["view", "copy", "edit", "reset_token", "disable", "delete"],
};
// 停用但落在时间窗口内：徽章必须显示「已停用」（停用优先于运行态）。
const LINK_DISABLED = {
  ...LINK_BASE, id: 13, name: "四班补考", status: "disabled", phase: "running",
  allowed_actions: ["view", "copy", "edit", "reset_token", "enable", "delete"],
};
// reviewer / 卷已转让的原作者：能读不能管。后端只下发打码串——exam_url 这个键
// 整个不出现（不是给 null），完整地址得走 reveal-url，那条路每次写审计。
const { exam_url: _fullUrlOmitted, ...READONLY_REST } = LINK_BASE;
const LINK_READONLY = {
  ...READONLY_REST, id: 14, name: "别人的场",
  exam_url_hint: "/exam/3f9a…2b1c",
  allowed_actions: ["view", "reveal_url"],
};
const REVEALED_URL = "/exam/3f9a1c7e2b4d8f2b1c";
// 归档卷的链接：只给「删除」（清理），不给增改。
const LINK_ARCHIVED = {
  ...LINK_BASE, id: 15, name: "旧卷的场", status: "disabled", phase: "ended",
  paper: { ...PAPERS[0], status: "archived" },
  allowed_actions: ["view", "copy", "delete"],
};
// 不限时 / 不限次数 / 无候考：通知文案的分支。
const LINK_UNLIMITED = {
  ...LINK_BASE, id: 16, name: "课后自测", open_at: null, close_at: null,
  duration_minutes: null, attempt_limit: 0, entry_open_minutes: 0, remind_minutes: "",
};

const ALL_LINKS = [LINK_BASE, LINK_DISABLED, LINK_READONLY, LINK_ARCHIVED, LINK_UNLIMITED];

const requests = [];
const calls = []; // {path, method, options}

vi.mock("../public/admin/admin-api.js", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    adminRequest: vi.fn(async (path, options = {}) => {
      const method = options.method || "GET";
      requests.push(path);
      calls.push({ path, method, options });
      if (path.startsWith("/exam-links?")) return { items: structuredClone(ALL_LINKS), total: ALL_LINKS.length, page: 1, size: 20 };
      if (path.startsWith("/exam-link-counts")) return { counts: { all: 5, active: 3, disabled: 2 } };
      if (path.startsWith("/papers?")) {
        // keyword=zzz 模拟「大量匹配」：total 远大于返回条数，下拉底部必须提示缩小范围。
        const keyword = new URLSearchParams(path.split("?")[1] || "").get("keyword");
        if (keyword === "zzz") return { items: structuredClone(PAPERS), total: 57, page: 1, size: 20 };
        if (keyword === "没有这卷") return { items: [], total: 0, page: 1, size: 20 };
        return { items: structuredClone(PAPERS), total: PAPERS.length, page: 1, size: 100 };
      }
      if (path.startsWith("/paper-owners")) return { items: [{ id: 1, display_name: "root" }] };
      if (/^\/papers\/\d+$/.test(path)) {
        // 999 模拟「不在前 100 条缓存、且当前账号不可见」的卷：拉详情被拒，走退化标签。
        if (path === "/papers/999") throw new Error("没有执行该试卷操作的权限。");
        const hit = PAPERS.find((p) => path === `/papers/${p.id}`);
        if (hit) return structuredClone(hit);
        throw new Error("试卷不存在。");
      }
      // reveal-url 必须排在通用 /links/{id} 之前，否则被它吞掉。
      if (/^\/links\/\d+\/reveal-url$/.test(path)) return { exam_url: REVEALED_URL };
      if (/^\/links\/\d+/.test(path)) return structuredClone(LINK_BASE); // disable/enable/reset/delete 的响应
      if (/^\/papers\/\d+\/links$/.test(path)) return structuredClone(LINK_BASE); // 新建
      throw new Error(`测试中未预料的请求：${method} ${path}`);
    }),
  };
});
vi.mock("../public/admin/admin-layout.js", () => ({ initLayout: vi.fn(), MENU: [] }));

const clipboard = vi.hoisted(() => ({ writeText: vi.fn(async () => {}) }));
Object.defineProperty(navigator, "clipboard", { value: clipboard, configurable: true });

function mountDom() {
  const html = readFileSync(PAGE_HTML, "utf-8");
  document.body.innerHTML = html.match(/<body>([\s\S]*?)<script/)[1];
}

const tick = async (rounds = 6) => {
  for (let i = 0; i < rounds; i += 1) await new Promise((r) => setTimeout(r, 0));
};

async function loadPage() {
  vi.resetModules();
  requests.length = 0;
  calls.length = 0;
  clipboard.writeText.mockClear();
  mountDom();
  await import("../public/admin/exam-links.js");
  await tick(8);
}

const $ = (id) => document.getElementById(id);
const rowOf = (id) => document.querySelector(`#linkRows tr[data-row="${id}"]`);
const confirmTopDialog = async () => {
  document.querySelector('.dialog-mask [data-role="confirm"]').click();
  await tick(6);
};

beforeEach(() => {
  document.body.innerHTML = "";
  history.pushState(null, "", "/"); // 各用例的 ?paper_id= 不互相串
});

describe("列表与徽章", () => {
  it("停用压过运行态：disabled 且窗口内的链接显示「已停用」，不是「进行中」", async () => {
    await loadPage();
    expect(rowOf(LINK_DISABLED.id).querySelector(".tag").textContent).toBe("已停用");
    expect(rowOf(LINK_BASE.id).querySelector(".tag").textContent).toBe("进行中");
    expect(rowOf(LINK_ARCHIVED.id).querySelector(".tag").textContent).toBe("已停用");
  });

  it("按钮完全按 allowed_actions 渲染：只读行只有查看 + 复制，归档卷的链接只有「删除」", async () => {
    await loadPage();
    const readonly = rowOf(LINK_READONLY.id);
    expect(readonly.querySelector("button[data-view]")).toBeTruthy();
    expect(readonly.querySelector("button[data-copy-notice]")).toBeTruthy(); // reveal_url 也能复制，只是背后留痕
    expect(readonly.querySelector("button[data-edit],button[data-reset],button[data-delete]")).toBeNull();

    const archived = rowOf(LINK_ARCHIVED.id);
    expect(archived.querySelector("button[data-delete]")).toBeTruthy();
    expect(archived.querySelector("button[data-edit],button[data-reset]")).toBeNull();
  });

  it("启停开关：状态即勾选态，能不能扳只看 allowed_actions", async () => {
    await loadPage();
    // 启用中 + 有 disable：开着、可扳。
    const base = rowOf(LINK_BASE.id).querySelector("input[data-toggle]");
    expect(base.checked).toBe(true);
    expect(base.disabled).toBe(false);
    // 停用中 + 有 enable：关着、可扳。
    const disabled = rowOf(LINK_DISABLED.id).querySelector("input[data-toggle]");
    expect(disabled.checked).toBe(false);
    expect(disabled.disabled).toBe(false);
    // 只读行与归档卷的链接：两头权限都没有，开关锁死。
    expect(rowOf(LINK_READONLY.id).querySelector("input[data-toggle]").disabled).toBe(true);
    expect(rowOf(LINK_ARCHIVED.id).querySelector("input[data-toggle]").disabled).toBe(true);
  });
});

describe("复制三件套与通知文案", () => {
  it("复制名称 / 复制链接 / 复制通知各自写进 clipboard", async () => {
    await loadPage();
    rowOf(LINK_BASE.id).querySelector("button[data-copy-name]").click();
    await tick(3);
    expect(clipboard.writeText).toHaveBeenLastCalledWith("三班期中考");
    rowOf(LINK_BASE.id).querySelector("button[data-copy-url]").click();
    await tick(3);
    expect(clipboard.writeText).toHaveBeenLastCalledWith(`${location.origin}/exam/3f9a1c`);
    rowOf(LINK_BASE.id).querySelector("button[data-copy-notice]").click();
    await tick(3);
    const notice = clipboard.writeText.mock.lastCall[0];
    expect(notice).toContain("【三班期中卷】三班期中考");
    expect(notice).toContain("限时 90 分钟");
    expect(notice).toContain("作答次数：1 次");
    expect(notice).toContain("可提前 15 分钟进入候考页");
  });

  it("buildNoticeText 分支：不限时 / 不限次数 / 无候考时文案跟着换", async () => {
    await loadPage();
    const { buildNoticeText } = await import("../public/admin/exam-links.js");
    const text = buildNoticeText(structuredClone(LINK_UNLIMITED), `${location.origin}/exam/3f9a1c`);
    expect(text).toContain("（不限时）");
    expect(text).toContain("作答次数：不限");
    expect(text).not.toContain("候考页"); // entry_open_minutes = 0 时提示行整行不出现
    expect(text).toContain("即日起 ~ 长期有效");
  });
});

describe("完整地址的取用与留痕", () => {
  it("无管理权的行只显示打码串，且整表照常渲染（exam_url 缺失不能打断渲染）", async () => {
    await loadPage();
    const readonly = rowOf(LINK_READONLY.id);
    expect(readonly.querySelector(".link-url").textContent).toBe("/exam/3f9a…2b1c");
    // 这一条才是关键：无条件 new URL(undefined) 会抛 TypeError 把整张表打断，
    // 所以后面几行必须还在。
    expect(document.querySelectorAll("#linkRows tr").length).toBe(ALL_LINKS.length);
    expect(rowOf(LINK_UNLIMITED.id)).toBeTruthy();
  });

  it("无管理权时复制先走 reveal-url 取完整地址，并明示已留痕", async () => {
    await loadPage();
    calls.length = 0;
    rowOf(LINK_READONLY.id).querySelector("button[data-copy-url]").click();
    await tick(4);
    const reveal = calls.find((call) => call.path === `/links/${LINK_READONLY.id}/reveal-url`);
    expect(reveal.method).toBe("POST");
    expect(clipboard.writeText).toHaveBeenLastCalledWith(`${location.origin}${REVEALED_URL}`);
    // 被记了要当场知道，不能等事后翻审计才发现。
    expect(document.querySelector(".toast-layer").textContent).toContain("已记入审计");
  });

  it("复制通知同样先取完整地址：文案里是真地址，不是打码串", async () => {
    await loadPage();
    rowOf(LINK_READONLY.id).querySelector("button[data-copy-notice]").click();
    await tick(4);
    const notice = clipboard.writeText.mock.lastCall[0];
    expect(notice).toContain(`${location.origin}${REVEALED_URL}`);
    expect(notice).not.toContain("…");
  });

  it("有管理权的行直接用行内地址，不发 reveal 请求", async () => {
    await loadPage();
    calls.length = 0;
    rowOf(LINK_BASE.id).querySelector("button[data-copy-url]").click();
    await tick(4);
    expect(calls.some((call) => call.path.includes("/reveal-url"))).toBe(false);
    expect(clipboard.writeText).toHaveBeenLastCalledWith(`${location.origin}/exam/3f9a1c`);
    expect(document.querySelector(".toast-layer").textContent).not.toContain("已记入审计");
  });
});

describe("删除与确认策略", () => {
  it("删除走 confirmDialog 且请求带 If-Match；取消时不发请求", async () => {
    await loadPage();
    calls.length = 0;
    rowOf(LINK_BASE.id).querySelector("button[data-delete]").click();
    await tick(4);
    const dialog = document.querySelector(".dialog-mask");
    expect(dialog.textContent).toContain("只是想暂停请用「停用」"); // 确认文案必须写出退路
    // 取消：不发请求
    document.querySelector('.dialog-mask [data-role="cancel"]').click();
    await tick(3);
    expect(calls.filter((c) => c.method === "DELETE")).toHaveLength(0);
    // 再来一次并确认：DELETE + If-Match = 行数据里的 revision
    rowOf(LINK_BASE.id).querySelector("button[data-delete]").click();
    await tick(4);
    await confirmTopDialog();
    const del = calls.find((c) => c.method === "DELETE" && c.path === `/links/${LINK_BASE.id}`);
    expect(del).toBeTruthy();
    expect(del.options.headers["If-Match"]).toBe(String(LINK_BASE.revision));
  });

  it("开关扳向「停」要确认（取消即扳回），扳向「开」不确认（可逆动作直接调用）", async () => {
    await loadPage();
    const toggle = rowOf(LINK_BASE.id).querySelector("input[data-toggle]");
    toggle.click(); // 扳向停
    await tick(4);
    expect(document.querySelector(".dialog-mask")).toBeTruthy();
    // 取消：不发请求，开关弹回「开」
    document.querySelector('.dialog-mask [data-role="cancel"]').click();
    await tick(3);
    expect(calls.some((c) => c.path.endsWith("/disable"))).toBe(false);
    expect(toggle.checked).toBe(true);
    // 再扳并确认
    toggle.click();
    await tick(4);
    await confirmTopDialog();
    expect(calls.some((c) => c.path.endsWith("/disable") && c.method === "POST")).toBe(true);

    calls.length = 0;
    rowOf(LINK_DISABLED.id).querySelector("input[data-toggle]").click(); // 扳向开
    await tick(4);
    expect(document.querySelector(".dialog-mask")).toBeNull(); // 无二次确认
    expect(calls.some((c) => c.path.endsWith("/enable") && c.method === "POST")).toBe(true);
  });
});

describe("学员实际体验 buildStudentPreview", () => {
  const BASE_FORM = {
    open_mode: "now", open_at: "", close_mode: "forever", close_at: "",
    duration_mode: "unlimited", duration_minutes: "", late_start_policy: "truncate",
    attempt_limit: 1, score_policy: "best", feedback_mode: "realtime",
    show_analysis: "after_submit", show_score: "immediate",
    notice: "", notice_ack_required: false, entry_open_minutes: 0, remind_minutes: "", warn_unanswered: true,
  };
  it("各分支：立即开放 / 有候考 / 有提醒点 / 不限时 / 结果公布", async () => {
    await loadPage();
    const { buildStudentPreview } = await import("../public/admin/exam-links.js");
    const immediate = buildStudentPreview(BASE_FORM);
    expect(immediate.lines.join("\n")).toContain("立即开放：学员随时可进入作答");
    expect(immediate.lines.join("\n")).toContain("不限时作答");
    expect(immediate.lines.join("\n")).toContain("长期有效");
    const full = buildStudentPreview({
      ...BASE_FORM,
      open_mode: "scheduled", open_at: "2026-06-10T14:00",
      close_mode: "scheduled", close_at: "2026-06-10T16:00",
      duration_mode: "limited", duration_minutes: "90",
      entry_open_minutes: 15, remind_minutes: "30,10,5",
    });
    const text = full.lines.join("\n");
    expect(text).toContain("2026-06-10 13:45 可进候考页");
    expect(text).toContain("2026-06-10 14:00 正式开考");
    expect(text).toContain("限时 90 分钟");
    expect(text).toContain("剩余 30/10/5 分钟提醒");
    expect(text).toContain("2026-06-10 16:00 统一关闭");
    expect(text).toContain("只有 1 次作答机会");
    expect(text).toContain("立即显示分数，交卷后显示解析");
  });

  it("迟到策略各有一句人话翻译（truncate / block / overrun）", async () => {
    await loadPage();
    const { buildStudentPreview } = await import("../public/admin/exam-links.js");
    const base = {
      ...BASE_FORM,
      open_mode: "scheduled", open_at: "2026-06-10T14:00",
      close_mode: "scheduled", close_at: "2026-06-10T16:00",
      duration_mode: "limited", duration_minutes: "90",
    };
    expect(buildStudentPreview({ ...base, late_start_policy: "truncate" }).lines.join("\n")).toContain("迟到者按关闭时间缩短作答时长");
    expect(buildStudentPreview({ ...base, late_start_policy: "block" }).lines.join("\n")).toContain("剩余不足 90 分钟禁止进场");
    expect(buildStudentPreview({ ...base, late_start_policy: "overrun" }).lines.join("\n")).toContain("允许超出关闭时间作答满时长");
  });

  it("冲突 / 无意义组合直接进 issues，不等保存", async () => {
    await loadPage();
    const { buildStudentPreview, collectIssues } = await import("../public/admin/exam-links.js");
    // 选了定时开放却没填时间：新模式下的「没填完」必须显式报出（旧设计靠留空猜意图）。
    expect(collectIssues({ ...BASE_FORM, open_mode: "scheduled" })[0]).toContain("还没填开放时间");
    expect(collectIssues({ ...BASE_FORM, close_mode: "scheduled" })[0]).toContain("还没填关闭时间");
    expect(collectIssues({ ...BASE_FORM, duration_mode: "limited" })[0]).toContain("还没填考试时长");
    // 提醒 ≥ 时长：永远不会触发的死配置。
    const dead = buildStudentPreview({
      ...BASE_FORM, duration_mode: "limited", duration_minutes: "30", remind_minutes: "30,10",
      close_mode: "scheduled", close_at: "2026-06-10T16:00",
    });
    expect(dead.issues.join("\n")).toContain("必须小于考试时长");
    // 开放 ≥ 关闭。
    expect(collectIssues({
      ...BASE_FORM, open_mode: "scheduled", open_at: "2026-06-10T16:00",
      close_mode: "scheduled", close_at: "2026-06-10T14:00",
    })[0]).toContain("开放时间必须早于关闭时间");
    // 立即开放时提前进候考页无意义：effectiveForm 直接归零，不再产生配置。
    expect(collectIssues({ ...BASE_FORM, entry_open_minutes: 15 })).toHaveLength(0);
  });

  it("Modal 里随表单实时重算：预览行与警告都就地更新", async () => {
    await loadPage();
    $("newLinkBtn").click();
    await tick(3);
    expect($("previewLines").textContent).toContain("立即开放");
    // 切到定时开放：时间输入出现；不填就先亮警告，不等保存。
    document.querySelector('input[name="lOpenMode"][value="scheduled"]').click();
    await tick(2);
    expect($("lOpenAtWrap").hidden).toBe(false);
    expect($("previewIssues").textContent).toContain("还没填开放时间");
    $("lOpenAt").value = "2026-06-10T14:00";
    $("lOpenAt").dispatchEvent(new Event("input", { bubbles: true }));
    document.querySelector('input[name="lDurationMode"][value="limited"]').click();
    $("lDuration").value = "90";
    $("lDuration").dispatchEvent(new Event("input", { bubbles: true }));
    await tick(2);
    expect($("previewLines").textContent).toContain("14:00 正式开考");
    expect($("previewLines").textContent).toContain("限时 90 分钟");
    expect($("previewIssues").hidden).toBe(true);
  });
});

describe("联动：无意义组合不让它停在界面上", () => {
  it("只允许作答一次时隐藏取分方式；改成多次后恢复", async () => {
    await loadPage();
    rowOf(LINK_BASE.id).querySelector("button[data-edit]").click(); // attempt_limit = 1
    await tick(3);
    expect($("lPolicyRow").hidden).toBe(true);
    $("lAttempt").value = "3";
    $("lAttempt").dispatchEvent(new Event("input", { bubbles: true }));
    await tick(2);
    expect($("lPolicyRow").hidden).toBe(false);
  });

  it("长期有效时截断策略禁用，已选中的自动退到「禁止开始」", async () => {
    await loadPage();
    $("newLinkBtn").click(); // 新建默认：长期有效 + 截断
    await tick(3);
    const truncate = document.querySelector('input[name="lLate"][value="truncate"]');
    expect(truncate.disabled).toBe(true);
    expect(document.querySelector('input[name="lLate"]:checked').value).toBe("block");
    // 给了关闭时间后截断恢复可选。
    document.querySelector('input[name="lCloseMode"][value="scheduled"]').click();
    await tick(2);
    expect(truncate.disabled).toBe(false);
  });

  it("须知为空时「必须阅读」自动禁用；写上须知后恢复（勾选状态保留）", async () => {
    await loadPage();
    rowOf(LINK_BASE.id).querySelector("button[data-edit]").click();
    await tick(3);
    expect($("lNoticeAck").disabled).toBe(true); // LINK_BASE.notice 为空
    $("lNotice").value = "请自备草稿纸";
    $("lNotice").dispatchEvent(new Event("input", { bubbles: true }));
    await tick(2);
    expect($("lNoticeAck").disabled).toBe(false);
  });
});

describe("Modal 可访问性（关闭后摘出可访问性树）", () => {
  it("mask 初始 hidden + inert；打开摘除；关闭恢复", async () => {
    await loadPage();
    const mask = $("linkMask");
    expect(mask.hidden).toBe(true);
    expect(mask.hasAttribute("inert")).toBe(true);
    $("newLinkBtn").click();
    await tick(3);
    expect(mask.hidden).toBe(false);
    expect(mask.hasAttribute("inert")).toBe(false);
    expect(mask.classList.contains("show")).toBe(true);
    $("linkCancel").click(); // 新建未改动，直接关闭
    await tick(3);
    expect(mask.hidden).toBe(true);
    expect(mask.hasAttribute("inert")).toBe(true);
  });

  it("关闭时间输入有自己的明确标签", async () => {
    await loadPage();
    const label = document.querySelector('label[for="lCloseAt"]');
    expect(label?.textContent).toContain("关闭时间");
  });
});

describe("新建链接的预设填充", () => {
  it("预设给的是定时考试：开放模式自动切到「定时开放」，候考与提醒不丢", async () => {
    await loadPage();
    $("newLinkBtn").click();
    await tick(3);
    // 通过组合框选中「期末模拟卷」：聚焦 → 下拉出结果 → 点选。
    $("lPaperInput").focus();
    await tick(4);
    const opt = [...document.querySelectorAll(".paper-option")].find((node) => node.textContent.includes("P000008"));
    expect(opt, "下拉结果里要有期末模拟卷").toBeTruthy();
    opt.click();
    await tick(2);
    expect($("lPaper").value).toBe("8"); // 点选后 id 写进 hidden input
    expect($("lPaperInput").value).toContain("期末模拟卷");
    expect(document.querySelector('input[name="lOpenMode"]:checked').value).toBe("scheduled");
    expect(document.querySelector('input[name="lDurationMode"]:checked').value).toBe("limited");
    expect($("lDuration").value).toBe("210");
    expect($("lEntryOpen").value).toBe("15");
    expect($("lEntryOpen").disabled).toBe(false); // 定时开放下候考可编辑
    expect($("lRemind").value).toBe("30,10,5");
    expect($("lNoticeAck").checked).toBe(true);
    expect($("lPaperHint").textContent).toContain("已按「模拟卷」填充");
    // 开放时间还没填：预览区就地提醒，而不是保存时才报错。
    expect($("previewIssues").textContent).toContain("还没填开放时间");
  });

  it("编辑既有链接时不填充预设；所属试卷用只读文本展示，不再给搜索框", async () => {
    await loadPage();
    rowOf(LINK_BASE.id).querySelector("button[data-edit]").click();
    await tick(3);
    expect($("lPaperPicker").hidden).toBe(true);
    expect($("lPaperStatic").hidden).toBe(false);
    expect($("lPaperStatic").textContent).toContain("P000007");
    expect($("lPaperStatic").textContent).toContain("三班期中卷");
    expect($("lName").value).toBe("三班期中考");
    expect($("lRemind").value).toBe("30,10,5"); // 老师调过的值原样呈现
    expect($("lPaperHint").textContent).not.toContain("填充");
    // 既有值反推模式：定时开放 + 指定关闭时间 + 限时作答。
    expect(document.querySelector('input[name="lOpenMode"]:checked').value).toBe("scheduled");
    expect(document.querySelector('input[name="lCloseMode"]:checked').value).toBe("scheduled");
    expect(document.querySelector('input[name="lDurationMode"]:checked').value).toBe("limited");
  });
});

describe("所属试卷组合框（远程搜索 + 数据量限制）", () => {
  it("聚焦即拉最近已发布卷（status=published、size=20），不防抖", async () => {
    await loadPage();
    $("newLinkBtn").click();
    await tick(3);
    calls.length = 0;
    $("lPaperInput").focus();
    await tick(4);
    const search = calls.find((c) => c.path.startsWith("/papers?"));
    expect(search.path).toContain("status=published");
    expect(search.path).toContain("size=20");
    expect(document.querySelectorAll(".paper-option").length).toBe(2);
    expect($("lPaperInput").getAttribute("aria-expanded")).toBe("true");
  });

  it("匹配超过 20 条时下拉底部提示缩小范围；无匹配时明说", async () => {
    await loadPage();
    $("newLinkBtn").click();
    await tick(3);
    $("lPaperInput").focus();
    await tick(4);
    $("lPaperInput").value = "zzz";
    $("lPaperInput").dispatchEvent(new Event("input", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 350)); // 300ms 防抖
    await tick(4);
    expect($("lPaperList").textContent).toContain("共 57 条匹配，仅显示前 2 条");
    $("lPaperInput").value = "没有这卷";
    $("lPaperInput").dispatchEvent(new Event("input", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 350));
    await tick(4);
    expect($("lPaperList").textContent).toContain("没有匹配的试卷");
  });

  it("重新输入即清除已选：未点选结果时保存被拦，不发请求", async () => {
    await loadPage();
    $("newLinkBtn").click();
    await tick(3);
    $("lPaperInput").focus();
    await tick(4);
    [...document.querySelectorAll(".paper-option")].find((node) => node.textContent.includes("P000007")).click();
    await tick(2);
    expect($("lPaper").value).toBe("7");
    // 改了一个字 = 放弃已选
    $("lPaperInput").value = "P000007x";
    $("lPaperInput").dispatchEvent(new Event("input", { bubbles: true }));
    expect($("lPaper").value).toBe("");
    $("lName").value = "随堂测";
    calls.length = 0;
    $("linkSaveBtn").click();
    await tick(3);
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
    expect(document.querySelector("#toastLayer .toast.error")?.textContent).toContain("点选所属试卷");
  });

  it("键盘：↓ 移动高亮、Enter 选中、Esc 关闭列表", async () => {
    await loadPage();
    $("newLinkBtn").click();
    await tick(3);
    $("lPaperInput").focus();
    await tick(4);
    $("lPaperInput").dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    const first = document.querySelector(".paper-option");
    expect(first.classList.contains("active")).toBe(true);
    expect($("lPaperInput").getAttribute("aria-activedescendant")).toBe(first.id);
    $("lPaperInput").dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await tick(2);
    expect($("lPaper").value).toBe(first.dataset.id);
    expect($("lPaperList").hidden).toBe(true);
  });

  it("?paper_id= 跳入后新建：预选这卷并触发预设（卷在缓存里）", async () => {
    history.pushState(null, "", "/admin/exam-links.html?paper_id=8");
    await loadPage();
    $("newLinkBtn").click();
    await tick(3);
    expect($("lPaper").value).toBe("8");
    expect($("lPaperInput").value).toContain("期末模拟卷");
    expect($("lDuration").value).toBe("210"); // 预设已填充
  });
});

describe("提醒规则的前端预检（与后端同语义，先拦省一次往返）", () => {
  it("提醒点 ≥ 时长：不发请求，toast 报错", async () => {
    await loadPage();
    rowOf(LINK_BASE.id).querySelector("button[data-edit]").click();
    await tick(3);
    $("lDuration").value = "30";
    $("lRemind").value = "30,10";
    calls.length = 0;
    $("linkSaveBtn").click();
    await tick(3);
    expect(calls.filter((c) => c.method === "PUT"), "死配置必须在前端拦下").toHaveLength(0);
    expect(document.querySelector("#toastLayer .toast.error")?.textContent).toContain("必须小于考试时长");
  });
});


describe("筛选栏的所属试卷组合框", () => {
  it("点选结果即应用筛选：列表请求带 paper_id，出现清除钮", async () => {
    await loadPage();
    $("sPaperInput").focus();
    await tick(4);
    const opt = [...document.querySelectorAll("#sPaperList .paper-option")].find((n) => n.textContent.includes("P000007"));
    expect(opt, "筛选栏下拉要能搜到卷（不限 status）").toBeTruthy();
    calls.length = 0;
    opt.click();
    await tick(4);
    expect($("sPaper").value).toBe("7");
    expect($("sPaperInput").value).toContain("三班期中卷");
    expect($("sPaperClear").hidden).toBe(false);
    expect(calls.some((c) => c.path.startsWith("/exam-links?") && c.path.includes("paper_id=7"))).toBe(true);
  });

  it("清除钮复位筛选 + 收掉跳入芯片；失焦未点选时文本还原，不留假状态", async () => {
    history.pushState(null, "", "/admin/exam-links.html?paper_id=8");
    await loadPage();
    expect($("sPaper").value).toBe("8");
    expect($("sPaperInput").value).toContain("期末模拟卷"); // 跳入预选落进组合框
    // 输入但不点选就失焦：还原成选中标签，不允许「字面像选了、其实没选」。
    $("sPaperInput").value = "随便敲的";
    $("sPaperInput").dispatchEvent(new FocusEvent("blur"));
    expect($("sPaperInput").value).toContain("期末模拟卷");
    expect($("sPaper").value).toBe("8");
    calls.length = 0;
    $("sPaperClear").click();
    await tick(4);
    expect($("sPaper").value).toBe("");
    expect($("sPaperInput").value).toBe("");
    expect($("sPaperClear").hidden).toBe(true);
    expect($("paperChip").hidden).toBe(true);
    expect(calls.some((c) => c.path.startsWith("/exam-links?") && !c.path.includes("paper_id"))).toBe(true);
  });
});

describe("URL 参数 ?paper_id=（评审回归：死分支 + 选择器注入）", () => {
  it("卷不在前 100 条缓存里：补退化选项 + 芯片照常显示，筛选仍然生效", async () => {
    history.pushState(null, "", "/admin/exam-links.html?paper_id=999");
    await loadPage();
    expect($("paperChip").hidden).toBe(false);
    expect($("paperChipText").textContent).toBe("试卷 #999"); // 详情拉不到就退化成编号
    expect($("sPaper").value).toBe("999");
    // 首屏请求就带着筛选，不是先闪一遍全量再收敛。
    expect(requests.find((p) => p.startsWith("/exam-links?"))).toContain("paper_id=999");
  });

  it("卷在缓存里：芯片用真名，不再多发一次详情请求", async () => {
    history.pushState(null, "", "/admin/exam-links.html?paper_id=8");
    await loadPage();
    expect($("paperChipText").textContent).toContain("P000008");
    expect(requests.filter((p) => p === "/papers/8")).toHaveLength(0);
  });

  it("恶意参数（?paper_id=\"]）打不白页面：忽略参数，全量列表照常加载", async () => {
    history.pushState(null, "", `/admin/exam-links.html?paper_id=${encodeURIComponent('"]')}`);
    await loadPage();
    expect($("paperChip").hidden).toBe(true);
    expect(rowOf(LINK_BASE.id)).toBeTruthy(); // 列表渲出来了，没有死在 bootstrap 半路
  });
});

describe("只读查看（reviewer / 别人的卷）", () => {
  it("只有 view 的行给「查看」，打开后输入全锁、没有保存键、关闭不问「放弃修改」", async () => {
    await loadPage();
    const readonly = rowOf(LINK_READONLY.id);
    expect(readonly.querySelector("button[data-edit]")).toBeNull();
    const viewBtn = readonly.querySelector("button[data-view]");
    expect(viewBtn, "view 不能是没人消费的死键").toBeTruthy();
    viewBtn.click();
    await tick(3);
    expect($("linkModalTitle").textContent).toBe("查看考试链接");
    expect($("linkSaveBtn").hidden).toBe(true);
    expect($("lName").disabled).toBe(true);
    expect($("lName").value).toBe("别人的场"); // 审核员要看的就是这些配置
    expect($("lRemind").value).toBe("30,10,5");
    $("linkCancel").click();
    await tick(3);
    expect(document.querySelector(".dialog-mask"), "只读查看没有未保存修改可言").toBeNull();
    expect($("linkMask").classList.contains("show")).toBe(false);
  });
});

describe("block 策略窗口预检（评审回归）", () => {
  it("block 策略下窗口短于时长：前端先拦，不发请求", async () => {
    await loadPage();
    rowOf(LINK_BASE.id).querySelector("button[data-edit]").click();
    await tick(3);
    document.querySelector('input[name="lLate"][value="block"]').click();
    $("lOpenAt").value = "2026-06-10T14:00";
    $("lCloseAt").value = "2026-06-10T14:30"; // 窗口 30 分钟
    $("lDuration").value = "60";
    calls.length = 0;
    $("linkSaveBtn").click();
    await tick(3);
    expect(calls.filter((c) => c.method === "PUT")).toHaveLength(0);
    expect(document.querySelector("#toastLayer .toast.error")?.textContent).toContain("没有任何人能开始作答");
  });
});
