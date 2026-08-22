// @vitest-environment jsdom
// 课时作业成绩页护栏测试。
//
// 起因：页面把「作业状态」下拉写死成 $("statusSelect")，而 HTML 早已改成由接口的
// filters 描述生成——元素不存在，读 .value 抛 "Cannot read properties of null"，
// 整页在首屏就死了。这页此前没有任何测试，所以 HTML / JS / 后端契约三方脱节了两代
// 都没人发现。本文件锁住「页面只按接口下发的 columns / stats / filters / cells 渲染」
// 这条契约本身，而不是锁某一列的文案。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { flushPromises } from "@vue/test-utils";

const requests = [];
let overviewPayload;
let detailPayload;
let historyPayload;
let recordPayload;

vi.mock("../public/admin/admin-layout.js", () => ({ initLayout: () => {} }));
vi.mock("../public/admin/admin-attempt-review.js", () => ({
  createAttemptReview: () => ({ open: vi.fn().mockResolvedValue(undefined) }),
}));
vi.mock("../public/admin/admin-api.js", () => ({
  adminRequest: (path) => {
    requests.push(path);
    if (path.startsWith("/lesson-homework-results")) return Promise.resolve(overviewPayload);
    if (path.endsWith("/attempts")) return Promise.resolve(historyPayload);
    if (path.endsWith("/results")) return Promise.resolve(detailPayload);
    if (path.includes("/records/")) return Promise.resolve(recordPayload);
    return Promise.reject(new Error(`未预期的请求：${path}`));
  },
}));

const OVERVIEW_COLUMNS = [
  { key: "homework", label: "作业", align: "left" },
  { key: "path", label: "所在章节 / 课时", align: "left" },
  { key: "deadline", label: "截止时间", align: "left", width: "170px" },
  { key: "people", label: "参与人数", align: "left" },
  { key: "submitted", label: "已交人数", align: "left" },
  { key: "attempts", label: "作答人次", align: "left" },
  { key: "avg", label: "平均成绩", align: "left" },
  { key: "pass_rate", label: "达标率", align: "left" },
  { key: "actions", label: "操作", align: "right" },
];

const DETAIL_COLUMNS = [
  { key: "name", label: "学员", align: "left" },
  { key: "attempt_count", label: "作答次数", align: "left" },
  { key: "tags", label: "状态", align: "left" },
  { key: "score", label: "计分成绩", align: "left" },
  { key: "duration", label: "用时", align: "left" },
  { key: "submit_kind", label: "交卷方式", align: "left" },
  { key: "started_at", label: "开始时间", align: "left" },
  { key: "submitted_at", label: "交卷时间", align: "left" },
  { key: "actions", label: "操作", align: "right" },
];

const DUE_ISO = "2026-08-20T02:00:00+00:00";
const START_ISO = "2026-08-16T01:00:00+00:00";
const SUBMIT_ISO = "2026-08-16T01:12:30+00:00";

const paperRow = () => ({
  source: "lesson_homework",
  source_id: 501,
  kind: "paper",
  kind_label: "试卷作业",
  detail_view: "attempts",
  course: { id: 1, title: "Python 入门" },
  section: { id: 11, title: "第一章 变量" },
  lesson: { id: 101, title: "第 1 课 认识变量" },
  homework: { id: 501, title: "第一课作业", due_at: DUE_ISO, status: "open" },
  subtitle: "P001 · 基础卷",
  deadline: { status: "open", label: "进行中", detail: `截止于 ${DUE_ISO}`, tone: "ok" },
  metrics: { people: 2, submitted: 1, attempts: 3 },
  cells: {
    homework: { text: "第一课作业", sub: "P001 · 基础卷", badge: "试卷作业" },
    path: { text: "第一章 变量", sub: "第 1 课 认识变量" },
    deadline: { text: "进行中", sub: `截止于 ${DUE_ISO}`, tone: "ok" },
    people: { text: "2" },
    submitted: { text: "1" },
    attempts: { text: "3" },
    avg: { text: "82 分" },
    pass_rate: { text: "100%" },
    actions: { actions: [{ type: "open_detail", label: "查看成绩" }] },
  },
});

function freshPayloads() {
  recordPayload = {
    title: "提交快照与反馈",
    note: "快照为提交时刻的不可变版本。",
    fields: [
      { label: "学员 / 挑战", value: "小明 · 迷宫" },
      { label: "判定结果", value: "已通过（规则通过 5/5）" },
      { label: "内容指纹", value: "sha256:abc123", tone: "muted" },
    ],
  };

  overviewPayload = {
    items: [paperRow()],
    total: 1,
    page: 1,
    size: 100,
    tree: [{
      id: 1,
      title: "Python 入门",
      sections: [{
        id: 11,
        title: "第一章 变量",
        lessons: [{ id: 101, title: "第 1 课 认识变量", homework_count: 1, kinds: { paper: 1 } }],
      }, {
        id: 12,
        title: "第二章 分支",
        lessons: [{ id: 102, title: "第 2 课 if", homework_count: 2, kinds: { paper: 2 } }],
      }],
    }],
    kinds: [],
    columns: OVERVIEW_COLUMNS,
    stats: [
      { key: "homework_count", label: "课时作业", text: "1" },
      { key: "people", label: "参与人数（当前范围）", text: "2" },
      { key: "submitted", label: "已交人数（当前范围）", text: "1" },
      { key: "attempts", label: "作答人次（当前范围）", text: "3" },
    ],
    filters: [
      { key: "kind", label: "作业类型", placeholder: "全部类型", options: [
        { value: "paper", label: "试卷作业", count: 1 },
        { value: "scratch", label: "Scratch 作业", count: 0 },
      ] },
      { key: "status", label: "作业状态", placeholder: "全部状态", options: [
        { value: "open", label: "进行中（含长期有效）" },
        { value: "closed", label: "已截止" },
      ] },
    ],
    server_now: "2026-08-17T08:00:00+00:00",
  };

  detailPayload = {
    ...paperRow(),
    full_score: 100,
    pass_score: 60,
    summary: { participants: 2, attempts: 3, submitted_participants: 1, avg: 82, min: 82, max: 82, pass_rate: 50 },
    distribution: [],
    students: [
      {
        user: { id: 9, username: "小明" },
        attempt_count: 2,
        row_id: "user-9",
        name: "小明",
        cells: {
          name: { text: "小明" },
          attempt_count: { text: "2" },
          tags: { badges: [{ label: "判题异常", tone: "danger" }] },
          score: { text: "82" },
          duration: { text: "12:30" },
          submit_kind: { text: "手动交卷" },
          started_at: { text: START_ISO },
          submitted_at: { text: SUBMIT_ISO },
          actions: { actions: [
            { type: "attempt_review", label: "答卷回看", attempt_id: 7001 },
            { type: "record_detail", label: "快照与反馈", record_id: 8001 },
            { type: "scratch_studio", label: "Studio 只读查看", challenge_id: 33, submission_id: 9001 },
          ] },
        },
        history_endpoint: "/lesson-homework/501/students/9/attempts",
      },
      {
        user: { id: 10, username: "小红" },
        attempt_count: 1,
        row_id: "user-10",
        name: "小红",
        cells: {
          name: { text: "小红" },
          attempt_count: { text: "1" },
          tags: { badges: [{ label: "未交卷", tone: "muted" }] },
          score: { text: "—" },
          duration: { text: "—" },
          submit_kind: { text: "—" },
          started_at: { text: "—" },
          submitted_at: { text: "—" },
          actions: { actions: [] },
        },
        history_endpoint: null,
      },
    ],
    stats: [
      { key: "people", label: "参与人数", text: "2" },
      { key: "attempts", label: "作答人次", text: "3" },
      { key: "submitted", label: "已交人数", text: "1" },
      { key: "avg", label: "平均分（按人）", text: "82" },
      { key: "range", label: "分数区间", text: "82 ~ 82" },
      { key: "pass_rate", label: "及格率（按人）", text: "50%" },
    ],
    tags: [
      { label: "试卷作业" },
      { label: "P001 · 基础卷" },
      { label: "进行中", tone: "ok" },
      { label: `截止于 ${DUE_ISO}`, tone: "muted" },
      { label: "满分 100 / 及格 60", tone: "muted" },
    ],
    columns: DETAIL_COLUMNS,
    insight: "统计按每位学员的最佳已交成绩计算。",
    empty_hint: "还没有学员开始这份作业",
    server_now: "2026-08-17T08:00:00+00:00",
  };

  historyPayload = {
    student: { user: { id: 9, username: "小明" }, attempt_count: 2 },
    columns: [
      { key: "attempt_no", label: "次数", align: "left" },
      { key: "status", label: "状态", align: "left" },
      { key: "score", label: "成绩", align: "left" },
      { key: "actions", label: "操作", align: "right" },
    ],
    rows: [
      { row_id: "attempt-7000", counted: false, cells: {
        attempt_no: { text: "第 1 次" }, status: { text: "已交卷" }, score: { text: "70" },
        actions: { actions: [{ type: "attempt_review", label: "答题详情", attempt_id: 7000 }] },
      } },
      { row_id: "attempt-7001", counted: true, cells: {
        attempt_no: { text: "第 2 次" }, status: { text: "已交卷" }, score: { text: "82" },
        actions: { actions: [{ type: "attempt_review", label: "答题详情", attempt_id: 7001 }] },
      } },
    ],
  };
}

// jsdom 会接管全局 URL，把 file: base 解析成 http://localhost:3000/...，
// 所以 HTML 路径不能用 new URL(...) 拼，改用 node:path（不受 jsdom 污染）。
const PAGE_HTML = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "../public/admin/homework-results.html"),
  "utf8",
);
const PAGE_BODY = PAGE_HTML.slice(PAGE_HTML.indexOf("<body>") + 6, PAGE_HTML.indexOf("</body>"))
  .replace(/<script[\s\S]*?<\/script>/g, "");

const $ = (id) => document.getElementById(id);
const text = (id) => $(id).textContent.replace(/\s+/g, " ").trim();
const lastRequest = () => requests[requests.length - 1];

async function bootPage() {
  document.body.innerHTML = PAGE_BODY;
  vi.resetModules();
  await import("../public/admin/homework-results.js");
  await flushPromises();
}

beforeEach(() => {
  vi.restoreAllMocks();
  requests.length = 0;
  freshPayloads();
});

describe("课时作业成绩 · 总览", () => {
  it("首屏加载不抛错，表头完全来自接口的 columns", async () => {
    await bootPage();
    const headers = [...$("overviewHead").querySelectorAll("th")].map((th) => th.textContent);
    expect(headers).toEqual(OVERVIEW_COLUMNS.map((column) => column.label));
    // 「操作」列的右对齐是列描述里的 align，不是页面写死的
    expect($("overviewHead").querySelector("th:last-child").className).toBe("col-right");
  });

  it("作业状态下拉由接口 filters 生成——本次线上报错的直接回归点", async () => {
    await bootPage();
    const select = $("statusSelect");
    expect(select).not.toBeNull();
    expect([...select.options].map((option) => option.value)).toEqual(["", "open", "closed"]);
    expect([...select.options].map((option) => option.textContent))
      .toEqual(["全部状态", "进行中（含长期有效）", "已截止"]);
  });

  it("行按 cells 渲染，主文本 / 次要行 / 徽标 / 语义色都取服务端下发的值", async () => {
    await bootPage();
    const cells = [...$("overviewRows").querySelectorAll("td")];
    expect(cells).toHaveLength(OVERVIEW_COLUMNS.length);
    expect(cells[0].textContent).toContain("第一课作业");
    expect(cells[0].textContent).toContain("P001 · 基础卷");
    expect(cells[0].querySelector(".tag").textContent).toBe("试卷作业");
    expect(cells[2].querySelector("b").className).toBe("tone-ok");
    expect(cells[6].textContent).toContain("82 分");
  });

  it("统计卡按接口 stats 渲染，页面不自己累加", async () => {
    await bootPage();
    const tiles = [...$("overviewStats").querySelectorAll(".stat")];
    expect(tiles).toHaveLength(4);
    expect(tiles[0].textContent).toContain("课时作业");
    expect(tiles[3].textContent).toContain("作答人次（当前范围）");
  });

  it("服务端下发的 ISO 时间落到本地格式，不把 ISO 串直接摆给老师看", async () => {
    await bootPage();
    const deadline = $("overviewRows").querySelectorAll("td")[2].textContent;
    expect(deadline).toContain("截止于 2026-08-");
    expect(deadline).not.toContain("T02:00:00");
  });

  it("首次请求不携带 kind，作业类型下拉由接口 filters 生成", async () => {
    await bootPage();
    expect(requests[0]).not.toContain("kind=");
    const select = $("kindSelect");
    expect(select).not.toBeNull();
    expect([...select.options].map((option) => option.value)).toEqual(["", "paper", "scratch"]);
    // 类型选项的计数（count）也来自 filters，不是页面自己数的
    expect([...select.options].map((option) => option.textContent))
      .toEqual(["全部类型", "试卷作业（1）", "Scratch 作业（0）"]);
  });
});

describe("课时作业成绩 · 筛选与目录", () => {
  it("点「筛选」不刷新页面，关键词与状态发给服务端而不是本页过滤", async () => {
    await bootPage();
    $("keywordInput").value = "  变量  ";
    $("statusSelect").value = "closed";
    const submit = new Event("submit", { bubbles: true, cancelable: true });
    $("filterForm").dispatchEvent(submit);
    await flushPromises();
    expect(submit.defaultPrevented).toBe(true);
    const params = new URLSearchParams(lastRequest().split("?")[1]);
    expect(params.get("keyword")).toBe("变量");
    expect(params.get("status")).toBe("closed");
    expect(params.get("page")).toBe("1");
  });

  it("选择作业类型后提交，kind 作为筛选条件交给服务端", async () => {
    await bootPage();
    $("kindSelect").value = "scratch";
    const submit = new Event("submit", { bubbles: true, cancelable: true });
    $("filterForm").dispatchEvent(submit);
    await flushPromises();
    expect(new URLSearchParams(lastRequest().split("?")[1]).get("kind")).toBe("scratch");
  });

  it("选择章节下拉后把 section_id 交给服务端，并保留课时级联选项", async () => {
    await bootPage();
    $("courseSelect").value = "1";
    $("courseSelect").dispatchEvent(new Event("change", { bubbles: true }));
    await flushPromises();
    expect($("sectionSelect").querySelectorAll("option")).toHaveLength(3);
    expect($("lessonSelect").disabled).toBe(true);
    overviewPayload = { ...overviewPayload, tree: [{ ...overviewPayload.tree[0], sections: [overviewPayload.tree[0].sections[0]] }] };
    $("sectionSelect").value = "11";
    $("sectionSelect").dispatchEvent(new Event("change", { bubbles: true }));
    await flushPromises();
    expect(new URLSearchParams(lastRequest().split("?")[1]).get("section_id")).toBe("11");
    expect($("lessonSelect").disabled).toBe(false);
    expect($("lessonSelect").querySelector('[value="101"]')).not.toBeNull();
    expect(text("activePath")).toBe("Python 入门 / 第一章 变量");
  });

  it("翻页走服务端，不在本页数据里切片", async () => {
    overviewPayload.total = 250;
    await bootPage();
    $("overviewFoot").querySelector('[data-page="next"]').click();
    await flushPromises();
    expect(new URLSearchParams(lastRequest().split("?")[1]).get("page")).toBe("2");
  });

  it("加载失败时亮出重试块，而不是留一张空白页", async () => {
    overviewPayload = null;
    await bootPage();
    expect($("overviewError").hidden).toBe(false);
    expect(text("overviewErrorText")).not.toBe("");
  });
});

describe("课时作业成绩 · 详情", () => {
  async function openDetail() {
    await bootPage();
    $("overviewRows").querySelector('[data-action*="open_detail"]').click();
    await flushPromises();
  }

  it("表头、统计卡、标签、口径说明全部来自接口", async () => {
    await openDetail();
    expect($("detailView").hidden).toBe(false);
    expect([...$("detailHead").querySelectorAll("th")].map((th) => th.textContent))
      .toEqual(DETAIL_COLUMNS.map((column) => column.label));
    expect($("detailStats").querySelectorAll(".stat")).toHaveLength(6);
    expect(text("detailKind")).toBe("试卷作业");
    expect(text("detailInsight")).toBe("统计按每位学员的最佳已交成绩计算。");
    expect(text("detailTags")).toContain("满分 100 / 及格 60");
    expect(text("detailTags")).not.toContain("T02:00:00");
  });

  it("学员行按 cells 渲染；只有服务端给了 history_endpoint 的行才有展开器", async () => {
    await openDetail();
    const rows = [...$("attemptRows").querySelectorAll("tr.data-row")];
    expect(rows).toHaveLength(2);
    expect(rows[0].querySelector(".expander")).not.toBeNull();
    expect(rows[1].querySelector(".expander")).toBeNull();
    expect(rows[0].querySelector(".cell-badges .tag").className).toContain("tone-danger");
    expect(rows[0].textContent).not.toContain("T01:12:30");
  });

  it("展开历史走服务端给的 history_endpoint，表格按 history.columns 渲染并标出计分那次", async () => {
    await openDetail();
    $("attemptRows").querySelector(".expander").click();
    await flushPromises();
    expect(lastRequest()).toBe("/lesson-homework/501/students/9/attempts");
    const host = document.querySelector(".history-host");
    expect(host.hidden).toBe(false);
    expect([...host.querySelectorAll("thead th")].map((th) => th.textContent))
      .toEqual(["次数", "状态", "成绩", "操作"]);
    // history-host 自身挂在 #attemptRows（一个 tbody）里，直接查 "tbody tr" 会把
    // 表头行也算进来（祖先链匹配）——所以限定到 .history-table 内。
    const bodyRows = [...host.querySelectorAll(".history-table tbody tr")];
    expect(bodyRows[0].textContent).not.toContain("计分");
    expect(bodyRows[1].textContent).toContain("计分");
  });

  it("再点一次收起，且不再重复请求", async () => {
    await openDetail();
    const expander = $("attemptRows").querySelector(".expander");
    expander.click();
    await flushPromises();
    const afterOpen = requests.length;
    expander.click();
    await flushPromises();
    expect(document.querySelector(".history-host").hidden).toBe(true);
    expander.click();
    await flushPromises();
    expect(requests).toHaveLength(afterOpen);
  });

  it("导出 CSV 按接口列生成，不认识任何作业类型专属字段", async () => {
    const blobs = [];
    globalThis.URL.createObjectURL = (blob) => { blobs.push(blob); return "blob:stub"; };
    globalThis.URL.revokeObjectURL = () => {};
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    await openDetail();
    $("exportBtn").click();
    const csv = await blobs[0].text();
    expect(csv).toContain("\"学员\",\"作答次数\",\"状态\",\"计分成绩\"");
    expect(csv).toContain("\"小明\"");
    expect(csv).toContain("\"判题异常\"");
    expect(csv).toContain("\"试卷作业 · P001 · 基础卷\"");
  });
});

describe("课时作业成绩 · 记录详情与 Studio", () => {
  it("record_detail 请求 /records/{id} 并把服务端字段填进 #recordMask", async () => {
    await bootPage();
    $("overviewRows").querySelector('[data-action*="open_detail"]').click();
    await flushPromises();
    $("attemptRows").querySelector('[data-action*="record_detail"]').click();
    await flushPromises();
    expect(lastRequest()).toBe("/lesson-homework/501/records/8001");
    expect($("recordMask").hidden).toBe(false);
    expect(text("recordTitle")).toBe("提交快照与反馈");
    expect([...$("recordFields").querySelectorAll("dt")].map((dt) => dt.textContent))
      .toEqual(["学员 / 挑战", "判定结果", "内容指纹"]);
    expect(text("recordNote")).toContain("不可变版本");
  });

  it("scratch_studio 以提交 id 打开 admin_review 只读快照", async () => {
    const opened = [];
    vi.spyOn(window, "open").mockImplementation((url, name, features) => { opened.push({ url, name, features }); return null; });
    await bootPage();
    $("overviewRows").querySelector('[data-action*="open_detail"]').click();
    await flushPromises();
    $("attemptRows").querySelector('[data-action*="scratch_studio"]').click();
    expect(opened).toHaveLength(1);
    expect(opened[0].url).toContain("mode=admin_review");
    expect(opened[0].url).toContain("submission_id=9001");
    expect(opened[0].name).toBe("_blank");
  });
});
