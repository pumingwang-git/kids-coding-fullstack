// @vitest-environment jsdom
// papers.js 页面级护栏（jsdom + 真实挂载 papers.html 的 body）。
// 与 paper-presets.test.js 分工：那里锁数据表，这里锁「页面有没有在对的时机用数据表」——
// 首屏一致性这条就是从真机实测走出来的：数据表完全正确，但 init 没调它。
//
// v2：组卷从独立页改为本页 Modal，考试链接独立成第二个 Modal。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const PAPERS_HTML = resolve(process.cwd(), "public/admin/papers.html");

const PICKABLE_ITEMS = [
  { id: 1, problem_id_no: "Q000001", type: "programming", sub_type: "cpp",
    title: "A+B Problem", stem_text: "输入两个整数，输出它们的和", difficulty: "入门", source: "洛谷", knowledge: [] },
  { id: 2, problem_id_no: "Q000002", type: "choice", sub_type: null,
    title: "HTML 语义化", stem_text: "HTML 语义化标签的作用", difficulty: "普及-", source: "原创", knowledge: [] },
];

// 列表里常驻两张卷：一张已发布（7）、一张草稿（8）。行操作按 allowed_actions 渲染，
// 所以点「编辑」进组卷弹窗这条真实路径可以直接在 jsdom 里走完。
const QUESTION = {
  problem_id_no: "Q000001", sort_order: 0, score: 100,
  problem: { id: 1, type: "programming", sub_type: "cpp", title: "A+B Problem", difficulty: "入门", status: "approved" },
};
const PUBLISHED = {
  id: 7, paper_id_no: "P000007", title: "三班期中卷", description: "", paper_type: "测试卷", subject: "cpp",
  ruleset: "IOI", score_mode: "testcase", partial_credit_multi: false, pass_score: 60, total_score: 100,
  status: "published", revision: 4, allowed_actions: ["view", "edit", "archive", "manage_links"],
  owner: { id: 1, display_name: "root" }, links: [], link_count: 0, active_link_count: 0,
  question_count: 1, question_types: { programming: 1 }, questions: [QUESTION],
};
const DRAFT = {
  ...PUBLISHED, id: 8, paper_id_no: null, title: "待发布卷", status: "draft", revision: 2,
  allowed_actions: ["view", "edit", "publish", "delete"],
};
// 归档卷：锁内容不锁记录——删除权放行（《4、后台考试链接-管理模块》2.2）。
const ARCHIVED = {
  ...PUBLISHED, id: 9, title: "上学期旧卷", status: "archived", revision: 6,
  allowed_actions: ["view", "delete", "transfer_owner"], link_count: 2, active_link_count: 0,
};

// ==================== 整卷预览的假数据（与后端 GET /papers/{id}/preview 契约一致） ====================
// 教师卷 = 学生卷 + 答案字段；学生卷里这些键整个不存在（不是给空值）。
const PV_CHOICE = { sort_order: 0, score: 20, problem_id_no: "Q000001", missing: false, type: "choice", sub_type: null, stem: "TCP 是面向连接的协议？" };
const PV_MULTI = { sort_order: 1, score: 20, problem_id_no: "Q000002", missing: false, type: "multi_choice", sub_type: null, stem: "哪些是传输层协议？" };
const PV_JUDGE = { sort_order: 2, score: 20, problem_id_no: "Q000003", missing: false, type: "judge", sub_type: null, stem: "UDP 是无连接的协议。" };
// 题干故意用「花括号里带答案」的写法（MathLive \placeholder{默认值} 语法的真实诱导）：
// 前后端正则一旦不一致，学生卷会把 {80} 连同答案原样印出来——这是泄漏回归护栏。
const PV_FILL = { sort_order: 3, score: 20, problem_id_no: "Q000004", missing: false, type: "fill", sub_type: null, stem: "HTTP 的默认端口是 \\placeholder[port]{80}。" };
const PV_PROG = { sort_order: 4, score: 20, problem_id_no: "Q000005", missing: false, type: "programming", sub_type: "cpp", stem: "输入两个整数，输出和。" };
const PV_BASE = {
  id: 7, paper_id_no: "P000007", title: "三班期中卷", description: "", paper_type: "测试卷",
  subject: "cpp", ruleset: "IOI", total_score: 100, pass_score: 60, score_mode: "testcase",
  partial_credit_multi: true, status: "published",
};
const PV_PROG_DETAIL = { title: "A+B Problem", input_format: "两个整数", output_format: "一个整数", hints: "无", time_limit_ms: 1000, memory_limit_mb: 256, samples: [{ input: "1 2", output: "3" }] };
const PREVIEW_STUDENT = {
  ...PV_BASE, with_answers: false,
  questions: [
    { ...PV_CHOICE, options: [{ label: "A", content: "对" }, { label: "B", content: "错" }] },
    { ...PV_MULTI, options: [{ label: "A", content: "TCP" }, { label: "B", content: "UDP" }, { label: "C", content: "IP" }] },
    { ...PV_JUDGE, options: [{ label: "A", content: "对" }, { label: "B", content: "错" }] },
    { ...PV_FILL },
    { ...PV_PROG, programming: PV_PROG_DETAIL },
  ],
};
const PREVIEW_TEACHER = {
  ...PV_BASE, with_answers: true,
  questions: [
    { ...PV_CHOICE, difficulty: "入门", source: "自命题", analysis: "三次握手建立连接。", options: [{ label: "A", content: "对", is_correct: true }, { label: "B", content: "错", is_correct: false }] },
    { ...PV_MULTI, difficulty: "普及", source: "CSP-J", analysis: "", options: [{ label: "A", content: "TCP", is_correct: true }, { label: "B", content: "UDP", is_correct: true }, { label: "C", content: "IP", is_correct: false }] },
    { ...PV_JUDGE, difficulty: "入门", source: "自命题", analysis: "", options: [{ label: "A", content: "对", is_correct: true }, { label: "B", content: "错", is_correct: false }] },
    { ...PV_FILL, difficulty: "入门", source: "自命题", analysis: "", blanks: [{ blank_index: 0, blank_key: "port", answer: "80" }] },
    { ...PV_PROG, difficulty: "普及-", source: "洛谷", analysis: "", programming: { ...PV_PROG_DETAIL, pass_condition: "全测试点通过", ref_code: { language: "cpp", code: "int main(){}" } } },
  ],
};

const requests = [];
const calls = []; // {path, method}：断言「有没有发出某个请求」用，比 requests 多一个方法维度
let previewTweak = null; // 单用例需要改造预览响应时挂的钩子（如把某题改成未过审）

vi.mock("../public/admin/admin-api.js", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    adminRequest: vi.fn(async (path, options = {}) => {
      const method = options.method || "GET";
      requests.push(path);
      calls.push({ path, method });
      if (path.startsWith("/problems/pickable")) {
        const keyword = new URLSearchParams(path.split("?")[1] || "").get("keyword");
        const items = keyword ? PICKABLE_ITEMS.filter((i) => i.problem_id_no === keyword.toUpperCase()) : PICKABLE_ITEMS;
        return { items, total: items.length, page: 1, size: 20 };
      }
      if (path.startsWith("/papers?")) return { items: [PUBLISHED, DRAFT, ARCHIVED], total: 3, page: 1, size: 20 };
      if (path.startsWith("/paper-status-counts")) return { counts: { draft: 1, published: 1, archived: 0 } };
      if (path.startsWith("/paper-owners")) return { items: [] };
      if (path.includes("/preview")) {
        const clone = structuredClone(path.includes("with_answers=1") ? PREVIEW_TEACHER : PREVIEW_STUDENT);
        if (previewTweak) previewTweak(clone);
        return clone;
      }
      for (const paper of [PUBLISHED, DRAFT, ARCHIVED]) {
        if (path === `/papers/${paper.id}`) {
          return method === "PUT" ? { ...paper, revision: paper.revision + 1 } : structuredClone(paper);
        }
        // 已发布卷再发布 → 后端 409；草稿发布 → 这里模拟一次校验失败（前端预判不到的那种）。
        if (path === `/papers/${paper.id}/publish`) {
          throw new Error(
            paper.status === "published"
              ? "试卷已发布，无需重复发布；直接保存修改即可生效。"
              : "以下题目未通过审核或已被删除，无法发布：Q000001",
          );
        }
      }
      throw new Error(`测试中未预料的请求：${path}`);
    }),
  };
});
vi.mock("../public/admin/admin-layout.js", () => ({ initLayout: vi.fn(), MENU: [] }));
// 渲染时序开关：默认纯微任务（快），竞态用例才打开跨宏任务。
// 真实 Vditor.preview 要等 lute WASM / i18n，必然跨宏任务；纯微任务的 mock 会让一整轮
// 渲染在单个宏任务里跑完，两轮渲染永远交织不起来——竞态类问题就此测不出来。
// inFlight/maxConcurrent 用来断言「真的并行了」——只看最终 DOM 是分不出串行和并行的。
const timing = vi.hoisted(() => ({ macrotask: false, inFlight: 0, maxConcurrent: 0 }));
// jsdom 没有 Vditor：renderMarkdown 用真实净化管线近似（保留 .blank-mark 产物，供填空回填断言）。
vi.mock("../public/admin/admin-markdown.js", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    renderMarkdown: vi.fn(async (container, markdown) => {
      timing.inFlight += 1;
      timing.maxConcurrent = Math.max(timing.maxConcurrent, timing.inFlight);
      try {
        if (timing.macrotask) await new Promise((r) => setTimeout(r, 0));
        const escaped = String(markdown || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);
        container.innerHTML = `<p>${actual.markBlanksInHtml(escaped)}</p>`;
        return true;
      } finally {
        timing.inFlight -= 1;
      }
    }),
  };
});

function mountPapersDom() {
  const html = readFileSync(PAPERS_HTML, "utf-8");
  const body = html.match(/<body>([\s\S]*?)<script/)[1];
  document.body.innerHTML = body;
}

const tick = async (rounds = 6) => {
  for (let i = 0; i < rounds; i += 1) await new Promise((r) => setTimeout(r, 0));
};

async function loadPage() {
  vi.resetModules();
  requests.length = 0;
  calls.length = 0;
  previewTweak = null;
  mountPapersDom();
  await import("../public/admin/papers.js");
  await tick();
}

// 点列表行的「编辑」进组卷弹窗（走的是用户真实路径：GET 详情 → openCompose）。
async function editPaper(id) {
  document.querySelector(`#paperRows button[data-edit="${id}"]`).click();
  await tick(6);
}
// 二次确认对话框由 admin-ui.js 现挂到 body 上，测试里替用户按下确认。
async function confirmTopDialog() {
  document.querySelector('.dialog-mask [data-role="confirm"]').click();
  await tick(6);
}

const $ = (id) => document.getElementById(id);
const checked = (name) => document.querySelector(`input[name="${name}"]:checked`)?.value;
const openCompose = () => $("newPaperBtn").click();

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("默认分区：已发布", () => {
  it("首屏请求就是 status=published，页签高亮在「已发布」", async () => {
    await loadPage();
    expect(requests.find((p) => p.startsWith("/papers?"))).toContain("status=published");
    expect(document.querySelector(".zone-tabs button.active").dataset.zone).toBe("published");
  });
});

describe("Modal 必须真的可见（真机实测发现的回归点）", () => {
  // admin.css 里 .modal-mask 默认 opacity:0 + pointer-events:none，只有加了 .show 才可见。
  // 曾经漏掉这一句：Modal 确实打开了（元素在、有尺寸），但完全透明 —— 用户体感是
  // 「点了没反应」，排查成本极高。jsdom 算不出 opacity，但 .show 类它测得了。
  it("打开组卷 Modal 会加上 .show，关闭会去掉", async () => {
    await loadPage();
    const mask = $("composeMask");
    expect(mask.classList.contains("show")).toBe(false);
    openCompose();
    await tick(2);
    expect(mask.classList.contains("show"), "缺 .show 则遮罩 opacity 恒为 0，看起来像没反应").toBe(true);
    $("composeCancel").click();
    await tick(3);
    expect(mask.classList.contains("show")).toBe(false);
  });

  it("markup 不该再用 hidden 控制遮罩：与 questions.html 统一走 .show", async () => {
    await loadPage();
    expect($("composeMask").hasAttribute("hidden")).toBe(false);
  });
});

describe("组卷 Modal 首屏一致性（评审实测发现的回归点）", () => {
  it("打开后，选中的 paper_type 与各字段值必须等于该预设", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    // 默认选中「练习卷」，字段值必须是练习卷预设展开后的值，而不是初始占位值。
    expect(checked("pType")).toBe("练习卷");
    expect(checked("pRuleset")).toBe("IOI");
    expect(checked("pScoreMode")).toBe("testcase");
    expect($("presetHint").textContent).toContain("练习卷");
  });

  it("切换预设走同一条填充路径：竞赛卷 → ACM + 全对得分", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    const acm = [...document.querySelectorAll('input[name="pType"]')].find((i) => i.value === "竞赛卷");
    acm.checked = true;
    acm.dispatchEvent(new Event("change", { bubbles: true }));
    await tick(2);
    expect(checked("pRuleset")).toBe("ACM");
    expect(checked("pScoreMode")).toBe("all_or_nothing");
    expect($("presetHint").textContent).toContain("竞赛卷");
  });

  it("切换预设只覆盖预设字段：已填的名称/说明/及格分不被重置", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    // 用户先敲自由文本，再切试卷类型——这是真实操作顺序，也是曾经的重置 bug
    $("pTitle").value = "三班期末卷";
    $("pTitle").dispatchEvent(new Event("input", { bubbles: true }));
    $("pDesc").value = "只给三班";
    $("pDesc").dispatchEvent(new Event("input", { bubbles: true }));
    $("pPassScore").value = "60";
    $("pPassScore").dispatchEvent(new Event("input", { bubbles: true }));
    const acm = [...document.querySelectorAll('input[name="pType"]')].find((i) => i.value === "竞赛卷");
    acm.checked = true;
    acm.dispatchEvent(new Event("change", { bubbles: true }));
    await tick(2);
    // 自由输入原样保留
    expect($("pTitle").value).toBe("三班期末卷");
    expect($("pDesc").value).toBe("只给三班");
    expect($("pPassScore").value).toBe("60");
    // 预设字段照常填充
    expect(checked("pRuleset")).toBe("ACM");
    expect(checked("pScoreMode")).toBe("all_or_nothing");
  });
});

describe("题号输入是组卷主路径", () => {
  it("题号:分值 成对解析：纯数字永远归前面最近的题号", async () => {
    const { parseIdScoreEntries } = await import("../public/admin/papers.js");
    // 冒号 / 空格 / 逗号混排等价
    expect(parseIdScoreEntries("Q000006:15 Q000007:15")).toEqual([
      { id: "Q000006", score: 15 },
      { id: "Q000007", score: 15 },
    ]);
    expect(parseIdScoreEntries("Q000004 20，Q000005 Q000006:15")).toEqual([
      { id: "Q000004", score: 20 },
      { id: "Q000005", score: null }, // 没等到分值，落默认分
      { id: "Q000006", score: 15 },
    ]);
    // 游离数字忽略：行首数字、一题跟两个数字、0 / 负数
    expect(parseIdScoreEntries("20 Q000004 10 30 Q000005 0 -5")).toEqual([
      { id: "Q000004", score: 10 },
      { id: "Q000005", score: null },
    ]);
    expect(parseIdScoreEntries("")).toEqual([]);
  });

  it("带分值的导入直接落到分值列", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    $("idInput").value = "Q000001:35 Q000002";
    $("parseIdsBtn").click();
    await tick(8);
    const scores = [...document.querySelectorAll(".score-input")].map((input) => input.value);
    expect(scores).toEqual(["35", "10"]); // 带分值的用导入值，没带的用默认 10
    expect($("totalScore").textContent).toBe("45");
  });

  it("换行 / 空格 / 逗号 / 顿号任意分隔都能解析", async () => {
    const { splitIdNos } = await import("../public/admin/papers.js");
    expect(splitIdNos("Q000001\nQ000002 Q000003,Q000004，Q000005、Q000006")).toEqual([
      "Q000001", "Q000002", "Q000003", "Q000004", "Q000005", "Q000006",
    ]);
    expect(splitIdNos("  q000001  ")).toEqual(["Q000001"]); // 小写归一
    expect(splitIdNos("")).toEqual([]);
  });

  it("解析后回填题干与题型，汇总条题数与总分同步", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    $("idInput").value = "Q000001 Q000002";
    $("parseIdsBtn").click();
    await tick(8);
    expect($("selectedRows").rows.length).toBe(2);
    expect($("selectedRows").textContent).toContain("A+B Problem");
    // 工具条徽章与汇总条两处题数必须同步——只更新一个是很容易漏的退化。
    expect($("totalScore").textContent).toBe("20");
    for (const node of document.querySelectorAll("#composeMask [data-question-count]")) {
      expect(node.textContent).toBe("2");
    }
  });

  it("解析不出来的题号不静默丢弃，留在列表里标红", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    $("idInput").value = "Q000001 Q999999";
    $("parseIdsBtn").click();
    await tick(8);
    expect($("selectedRows").rows.length).toBe(2);
    expect($("selectedRows").textContent).toContain("题号不存在或未过审");
  });

  it("改分值后总分即时汇总，题数不变", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    $("idInput").value = "Q000001";
    $("parseIdsBtn").click();
    await tick(8);
    const input = document.querySelector(".score-input");
    input.value = "45";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    expect($("totalScore").textContent).toBe("45");
    for (const node of document.querySelectorAll("#composeMask [data-question-count]")) {
      expect(node.textContent).toBe("1");
    }
  });
});

describe("题库选题收进抽屉（新布局：主列表 + 添加抽屉）", () => {
  it("抽屉默认关闭，点「从题库添加」后打开并加载题库", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    expect($("composeRight").classList.contains("is-drawer-open")).toBe(false);
    $("openLibrary").click();
    await tick(6);
    expect($("composeRight").classList.contains("is-drawer-open")).toBe(true);
    expect($("bankRows").rows.length).toBe(2);
    expect($("bankRows").textContent).toContain("Q000001");
  });

  it("可直接加入，已选题的按钮变「已加入」置灰不产生重复行", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    $("openLibrary").click();
    await tick(6);
    const first = $("bankRows").querySelector("button[data-add]");
    first.click();
    await tick(6);
    expect($("selectedRows").rows.length).toBe(1);
    const again = $("bankRows").querySelector('button[data-add="Q000001"]');
    expect(again.disabled).toBe(true);
    expect(again.textContent).toBe("已加入");
    again.click(); // 强制再点也不该重复
    await tick(2);
    expect($("selectedRows").rows.length).toBe(1);
  });
});

describe("已选题目拖拽排序", () => {
  it("⠿ 手柄按住才放行拖拽，拖到目标行下半部插到其后", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    $("idInput").value = "Q000001 Q000002";
    $("parseIdsBtn").click();
    await tick(8);
    const tbody = $("selectedRows");
    const row0 = tbody.rows[0];
    // 手柄按住才放行 draggable，避免误拖文本
    row0.querySelector(".drag-grip").dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    expect(row0.draggable).toBe(true);
    // 拖到第 2 行下半部 → 插到其后（jsdom 的 getBoundingClientRect 全 0，clientY>0 即下半部）
    row0.dispatchEvent(Object.assign(new Event("dragstart", { bubbles: true }), { dataTransfer: {} }));
    tbody.rows[1].dispatchEvent(Object.assign(new Event("drop", { bubbles: true, cancelable: true }), { clientY: 999 }));
    await tick(2);
    const ids = [...tbody.rows].map((tr) => tr.cells[1].textContent);
    expect(ids).toEqual(["Q000002", "Q000001"]);
    // 拖拽状态必须清理干净，不能留着 draggable / 指示线
    expect([...tbody.rows].some((tr) => tr.draggable)).toBe(false);
    expect(tbody.querySelector(".dragging, .drop-before, .drop-after")).toBeNull();
  });
});

describe("及格分不能超过总分", () => {
  it("超过即时标红；总分降下去后，原来合法的及格分也会亮提示", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    $("idInput").value = "Q000001 Q000002"; // 总分 20
    $("parseIdsBtn").click();
    await tick(8);
    $("pPassScore").value = "15";
    $("pPassScore").dispatchEvent(new Event("input", { bubbles: true }));
    expect($("passScoreWarn").hidden).toBe(true); // 15 ≤ 20，合法不提示
    // 删一道题总分降到 10 → 原本合法的 15 变非法，必须亮提示
    $("selectedRows").querySelector("button[data-remove]").click();
    await tick(2);
    expect($("totalScore").textContent).toBe("10");
    expect($("passScoreWarn").hidden).toBe(false);
    expect($("passScoreWarn").textContent).toContain("10");
    expect($("pPassScore").classList.contains("input-invalid")).toBe(true);
    // 改回合法值，提示消失
    $("pPassScore").value = "5";
    $("pPassScore").dispatchEvent(new Event("input", { bubbles: true }));
    expect($("passScoreWarn").hidden).toBe(true);
    expect($("pPassScore").classList.contains("input-invalid")).toBe(false);
  });
});

describe("已发布卷的编辑（真机实测发现的回归点：假失败 + 假「未保存」）", () => {
  // 现场表现：改完已发布卷点「保存并发布」→ toast「没有执行该试卷操作的权限」，
  // 但 PUT 其实已经成功落库；关弹窗还问「放弃未保存的修改？」，点了也放弃不掉。
  // 根因是底栏对已发布卷仍摆着「保存并发布」，而 published 卷根本没有 publish 这个动作。
  it("底栏按状态渲染：已发布卷只给「保存修改」，不给「保存并发布」", async () => {
    await loadPage();
    await editPaper(PUBLISHED.id);
    expect($("publishBtn").hidden, "已发布卷点它必定 409，不能摆出来").toBe(true);
    expect($("saveBtn").hidden).toBe(false);
    expect($("saveBtn").textContent).toBe("保存修改");
    expect($("composeHint").textContent).toContain("立即对已分发的考试链接生效");
    // 草稿卷保持原样：两个按钮都在。
    $("composeCancel").click();
    await tick(3);
    await editPaper(DRAFT.id);
    expect($("publishBtn").hidden).toBe(false);
    expect($("saveBtn").textContent).toBe("保存草稿");
  });

  it("保存已发布卷只发一次 PUT，绝不再打 /publish", async () => {
    await loadPage();
    await editPaper(PUBLISHED.id);
    $("pTitle").value = "三班期中卷（改）";
    $("pTitle").dispatchEvent(new Event("input", { bubbles: true }));
    calls.length = 0;
    $("saveBtn").click();
    await tick(8);
    expect(calls.filter((c) => c.method === "PUT" && c.path === `/papers/${PUBLISHED.id}`)).toHaveLength(1);
    expect(calls.filter((c) => c.path.endsWith("/publish")), "重复发布会被后端 409 挡回，白造一次半成功写入").toHaveLength(0);
    expect($("composeMask").classList.contains("show")).toBe(false);
  });

  it("二道保险：已发布卷即使触发到发布按钮，也不许发出 /publish", async () => {
    await loadPage();
    await editPaper(PUBLISHED.id);
    calls.length = 0;
    $("publishBtn").click(); // 按钮已隐藏，这里模拟隐藏失效/旧 DOM 残留的情况
    await tick(3);
    if (document.querySelector(".dialog-mask")) await confirmTopDialog();
    await tick(6);
    expect(calls.filter((c) => c.path.endsWith("/publish"))).toHaveLength(0);
  });

  it("PUT 成功后即使后续步骤失败，也不能再谎称「未保存」", async () => {
    await loadPage();
    await editPaper(DRAFT.id); // 草稿：PUT 会成功，紧跟的 publish 会被后端校验拒掉
    $("pTitle").value = "改过名字了";
    $("pTitle").dispatchEvent(new Event("input", { bubbles: true }));
    $("publishBtn").click();
    await tick(3);
    await confirmTopDialog(); // 「确认发布」
    expect(calls.some((c) => c.method === "PUT" && c.path === `/papers/${DRAFT.id}`), "第一步应当已经落库").toBe(true);
    expect($("composeMask").classList.contains("show"), "发布失败，弹窗保持打开让用户改").toBe(true);
    // 关键：改动已经进库了，关闭时不该再弹「放弃未保存的修改？」——那个「放弃」根本放弃不掉。
    $("composeCancel").click();
    await tick(4);
    expect(document.querySelector(".dialog-mask"), "改动已落库却提示未保存，是在骗用户").toBeNull();
    expect($("composeMask").classList.contains("show")).toBe(false);
  });
});

describe("安全红线：选题只能调 pickable", () => {
  it("整个组卷流程中不出现 /problems/{id} 详情接口", async () => {
    await loadPage();
    openCompose();
    await tick(2);
    $("openLibrary").click();
    await tick(6);
    $("idInput").value = "Q000001";
    $("parseIdsBtn").click();
    await tick(8);
    const problemCalls = requests.filter((path) => path.startsWith("/problems"));
    expect(problemCalls.length).toBeGreaterThan(0);
    for (const path of problemCalls) {
      expect(path, `${path} 不是 pickable —— 详情接口会把答案发进浏览器`).toMatch(/^\/problems\/pickable/);
    }
  });
});


describe("整卷预览", () => {
  const previewCalls = () => calls.filter((c) => c.path.includes("/preview"));
  const sheet = () => $("paperPreviewSheet");
  const openPreviewFromRow = async (id) => {
    document.querySelector(`#paperRows button[data-preview="${id}"]`).click();
    await tick(10);
  };
  const pickVariant = (value) => document.querySelector(`input[name="pvVariant"][value="${value}"]`).click();

  it("教师卷：五题型结构完整（小节/样例/限制/答案区/半分提示/档案信息/填空回填）", async () => {
    await loadPage();
    await openPreviewFromRow(PUBLISHED.id);
    document.querySelector('input[name="pvVariant"][value="teacher"]').click();
    await tick(12);
    expect(sheet().querySelectorAll("section.q")).toHaveLength(5);
    // 操作题小节顺序：题面 → 输入格式 → 输出格式 → 样例 → 说明/提示 → 限制。
    const prog = sheet().querySelector('section.q[data-q="4"]');
    expect(prog.textContent).toContain("输入格式");
    expect(prog.textContent).toContain("输出格式");
    expect(prog.textContent).toContain("说明 / 提示");
    expect(prog.querySelectorAll(".samples pre")).toHaveLength(2);
    expect(prog.querySelector(".limits").textContent).toContain("1000 ms");
    expect(prog.querySelector(".answer-box").textContent).toContain("int main(){}");
    expect(prog.querySelector(".answer-box").textContent).toContain("全测试点通过");
    // 答案区每题都有；正确选项标记共 4 个（单选 1 + 多选 2 + 判断 1）。
    expect(sheet().querySelectorAll(".answer-box")).toHaveLength(5);
    expect(sheet().querySelectorAll(".options li.correct")).toHaveLength(4);
    // 卷顶警示条、题头档案信息、多选半分提示（卷子开了 partial_credit_multi）。
    expect(sheet().querySelector(".teacher-banner")).toBeTruthy();
    expect(sheet().querySelectorAll(".q-admin")).toHaveLength(5);
    expect(sheet().querySelector(".half-note")).toBeTruthy();
    // 填空答案填回原位（.filled），不是另起一行。
    expect(sheet().querySelector(".blank-mark.filled")?.textContent).toBe("80");
    // 答题留白只在学生卷生效：教师卷既不渲染留白，开关也藏起来。
    expect(sheet().querySelector(".answer-space")).toBeFalsy();
    expect($("pvSpaceLine").hidden).toBe(true);
  });

  it("学生卷：DOM 里没有任何答案特征（答案区/警示条/正确标记/档案信息/参考代码）", async () => {
    await loadPage();
    await openPreviewFromRow(PUBLISHED.id);
    expect($("pvSpaceLine").hidden).toBe(false);
    expect(sheet().querySelector(".answer-box")).toBeFalsy();
    expect(sheet().querySelector(".teacher-banner")).toBeFalsy();
    expect(sheet().querySelector(".options li.correct")).toBeFalsy();
    expect(sheet().querySelector(".q-admin")).toBeFalsy();
    expect(sheet().textContent).not.toContain("参考答案");
    expect(sheet().textContent).not.toContain("参考代码");
    expect(sheet().textContent).not.toContain("int main");
    // 泄漏回归：题干里 \\placeholder[port]{80} 的 {80} 绝不能原样印上学生卷。
    expect(sheet().textContent).not.toContain("placeholder");
    expect(sheet().textContent).not.toContain("{80}");
    // 填空保持空横线；答题留白渲染了但默认关，勾选后 sheet[data-space] 切到 on。
    const blank = sheet().querySelector(".blank-mark");
    expect(blank).toBeTruthy();
    expect(blank.classList.contains("filled")).toBe(false);
    expect(blank.textContent).toBe("");
    expect(sheet().querySelectorAll(".answer-space").length).toBeGreaterThan(0);
    expect(sheet().dataset.space).toBe("off");
    $("pvAnswerSpace").click();
    await tick(2);
    expect(sheet().dataset.space).toBe("on");
  });

  it("组卷有未保存改动时点预览：先弹「预览需要先保存」，确认前不发预览请求；确认后保存并预览且弹窗不关", async () => {
    await loadPage();
    await editPaper(DRAFT.id);
    $("pTitle").value = "改过的名字";
    $("pTitle").dispatchEvent(new Event("input", { bubbles: true }));
    $("openPreviewBtn").click();
    await tick(4);
    expect(previewCalls(), "确认对话框出来之前绝不能发预览请求").toHaveLength(0);
    const dialog = document.querySelector(".dialog-mask");
    expect(dialog).toBeTruthy();
    expect(dialog.textContent).toContain("预览需要先保存");
    await confirmTopDialog(); // 「保存并预览」
    await tick(12);
    expect(calls.some((c) => c.method === "PUT" && c.path === `/papers/${DRAFT.id}`), "先落库再预览").toBe(true);
    expect(previewCalls().map((c) => c.path)).toEqual([`/papers/${DRAFT.id}/preview?with_answers=0`]);
    // keepOpen：保存后组卷弹窗保持打开，预览压在上面。
    expect($("composeMask").classList.contains("show")).toBe(true);
    expect($("paperPreviewMask").hidden).toBe(false);
  });

  it("切换卷别 = 重新发请求（不是 CSS 切换），with_answers 参数正确", async () => {
    await loadPage();
    await openPreviewFromRow(PUBLISHED.id);
    expect(previewCalls().map((c) => c.path)).toEqual([`/papers/${PUBLISHED.id}/preview?with_answers=0`]);
    document.querySelector('input[name="pvVariant"][value="teacher"]').click();
    await tick(10);
    document.querySelector('input[name="pvVariant"][value="student"]').click();
    await tick(10);
    expect(previewCalls().map((c) => c.path)).toEqual([
      `/papers/${PUBLISHED.id}/preview?with_answers=0`,
      `/papers/${PUBLISHED.id}/preview?with_answers=1`,
      `/papers/${PUBLISHED.id}/preview?with_answers=0`,
    ]);
  });

  it("未过审的题在题头标「未过审」角标（与 missing 同一套提示语言，两种卷别都标）", async () => {
    await loadPage();
    // 钩子在 loadPage 之后挂：loadPage 会重置 previewTweak。
    previewTweak = (paper) => { paper.questions[0].approved = false; };
    await openPreviewFromRow(PUBLISHED.id);
    const badge = () => sheet().querySelector('section.q[data-q="0"] .q-head .tag.danger');
    expect(badge()?.textContent).toContain("未过审");
    expect(sheet().querySelectorAll('section.q .tag.danger')).toHaveLength(1); // 只有这一题标
    // 教师卷同样要标：拿着答案核对时更得知道这题发布会拒。
    document.querySelector('input[name="pvVariant"][value="teacher"]').click();
    await tick(10);
    expect(badge()?.textContent).toContain("未过审");
  });

  // 评审实测发现的回归点：切到教师卷、趁渲染没跑完再切回学生卷，
  // 旧那一轮渲染会把答案写进已经换成学生卷的卷面——老师此时直接打印，
  // 印出来就是一张带答案的学生卷。根因是渲染循环里重新 querySelector(previewSheet)
  // 拿到了新 DOM 的节点（见 papers.js 的 pvRender 节点快照注释）。
  it("卷别快切：教师卷渲染途中切回学生卷，答案不能落进学生卷", { timeout: 30000 }, async () => {
    timing.macrotask = true; // 必须跨宏任务，否则一整轮渲染在单个宏任务里跑完，交织不起来
    try {
      const leaks = [];
      for (const delay of [0, 1, 2, 3]) {
        await loadPage();
        await openPreviewFromRow(PUBLISHED.id);
        await tick(20);
        pickVariant("teacher");
        await tick(delay); // 教师卷渲染进行到不同阶段
        pickVariant("student");
        await tick(40);

        const isTeacherView = !!sheet().querySelector(".teacher-banner");
        const blanks = [...sheet().querySelectorAll(".blank-mark")].map((n) => n.textContent);
        if (!isTeacherView && (blanks.some((t) => t !== "") || sheet().textContent.includes("参考答案"))) {
          leaks.push({ delay, 空位内容: blanks, 含参考答案: sheet().textContent.includes("参考答案") });
        }
      }
      expect(leaks, `学生卷上渲染出了教师卷答案：${JSON.stringify(leaks)}`).toEqual([]);
    } finally {
      timing.macrotask = false;
    }
  });

  it("焦点跟着预览走：打开落到关闭按钮、Tab 环在层内、关闭还给打开它的按钮", async () => {
    await loadPage();
    const opener = document.querySelector(`#paperRows button[data-preview="${PUBLISHED.id}"]`);
    opener.focus();
    await openPreviewFromRow(PUBLISHED.id);
    expect(document.activeElement).toBe($("paperPreviewClose"));
    // Tab 环挂在 .preview-dialog 上：容器内按 Tab 不会把焦点漏到底下的列表
    const dialog = $("paperPreviewMask").querySelector(".preview-dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
    $("paperPreviewClose").click();
    await tick(4);
    expect(document.activeElement).toBe(opener);
  });

  it("按题并行渲染：题与题之间不串行，且填空回填仍落在本题渲完之后", async () => {
    timing.macrotask = true; // 串行/并行的差别只有跨宏任务时才看得出来
    try {
      await loadPage();
      await openPreviewFromRow(PUBLISHED.id);
      await tick(40); // 等学生卷这一轮彻底渲完，免得把「两轮重叠」误当成「按题并行」
      expect(timing.inFlight, "上一轮还没渲完，并发度读数不干净").toBe(0);
      timing.maxConcurrent = 0;
      pickVariant("teacher");
      await tick(40);
      // 真的并行了：串行渲染的并发度恒为 1，只看最终 DOM 分不出串行和并行。
      expect(timing.maxConcurrent, "题与题之间仍是串行的").toBeGreaterThan(1);
      // 5 题各自渲完：结构齐全 + 填空答案确实填回了原位（并行没打乱本题内部时序）
      expect(sheet().querySelectorAll("section.q")).toHaveLength(5);
      expect(sheet().querySelectorAll(".answer-box")).toHaveLength(5);
      expect(sheet().querySelector(".blank-mark.filled")?.textContent).toBe("80");
      // 每个 md-slot 都真的渲染过，没有因为并行漏掉
      expect([...sheet().querySelectorAll(".md-slot")].every((s) => s.children.length > 0)).toBe(true);
    } finally {
      timing.macrotask = false;
    }
  });
});


describe("考试链接入口已迁往独立页面（《4、后台考试链接-管理模块》）", () => {
  it("「考试链接」是指向 exam-links.html?paper_id= 的 <a>，不再是开 Modal 的按钮", async () => {
    await loadPage();
    const anchor = document.querySelector(`#paperRows a[href="exam-links.html?paper_id=${PUBLISHED.id}"]`);
    expect(anchor, "应渲染为链接：中键新开标签是「一边看卷一边配链接」的常见动作").toBeTruthy();
    expect(anchor.textContent).toBe("考试链接");
    // 链接 Modal 已整块迁走：页面里不该再有它的 DOM 与按钮。
    expect($("linksMask")).toBeNull();
    expect(document.querySelector("#paperRows button[data-links]")).toBeNull();
    // 草稿卷没有 manage_links，入口不出现。
    expect(document.querySelector(`#paperRows a[href="exam-links.html?paper_id=${DRAFT.id}"]`)).toBeNull();
  });
});

describe("归档卷的删除（锁内容不锁记录）", () => {
  it("归档卷行有「删除」，确认文案是归档版（链接数 + 编号不回收）", async () => {
    await loadPage();
    const del = document.querySelector(`#paperRows button[data-delete="${ARCHIVED.id}"]`);
    expect(del, "归档卷的 allowed_actions 含 delete，按钮必须渲染出来").toBeTruthy();
    del.click();
    await tick(4);
    const dialog = document.querySelector(".dialog-mask");
    expect(dialog).toBeTruthy();
    expect(dialog.textContent).toContain("2 条考试链接一并销毁");
    expect(dialog.textContent).toContain("P000007");
    expect(dialog.textContent).not.toContain("草稿删除后不可恢复");
    calls.length = 0;
    await confirmTopDialog();
    const delCall = calls.find((c) => c.method === "DELETE" && c.path === `/papers/${ARCHIVED.id}`);
    expect(delCall, "确认后才允许发 DELETE").toBeTruthy();
  });

  it("草稿的确认文案仍是草稿版，两种文案不串", async () => {
    await loadPage();
    document.querySelector(`#paperRows button[data-delete="${DRAFT.id}"]`).click();
    await tick(4);
    const dialog = document.querySelector(".dialog-mask");
    expect(dialog.textContent).toContain("草稿删除后不可恢复。");
    expect(dialog.textContent).not.toContain("考试链接一并销毁");
  });
});
