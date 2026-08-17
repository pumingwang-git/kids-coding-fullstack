// @vitest-environment jsdom
// 管理端共用 ES 模块的护栏测试：admin-list.js / admin-tagtree.js 被多个页面共用，
// 改一处炸四处——这些用例就是「炸」发生时的报警器。
// 覆盖：escapeHtml/ifMatch 单源导出、知识点树交互、内联校验路由、列表三态与分页。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createKnowledgeTree } from "../public/admin/admin-tagtree.js";
import { createPagedList, skeletonRows } from "../public/admin/admin-list.js";
import { clearFieldErrors, escapeHtml, showFieldErrors } from "../public/admin/admin-ui.js";
import { ifMatch } from "../public/admin/admin-api.js";
import { markBlanksInHtml } from "../public/admin/admin-markdown.js";

function mountDom() {
  document.body.innerHTML = `
    <div id="ktTrigger"><span id="ktHint">请选择</span></div>
    <div id="ktPop" hidden><input id="ktFilter" /><ul id="ktTree"></ul></div>
    <div id="ktSummary"></div>
    <table><tbody id="rows"></tbody></table>
    <div id="emptyTip" hidden></div><div id="errorTip" hidden><span id="errorText"></span></div>
    <div id="totalTip"></div>
    <button id="prevBtn"></button><button id="nextBtn"></button><button id="retryBtn"></button>
    <select id="pageSizeSel"><option>10</option><option selected>20</option></select>
    <input type="checkbox" id="checkAll" />
    <label class="field"><input id="f1" /></label>
    <div id="optionsError" hidden></div>
    <div class="card"><input name="correctOption" type="radio" /></div>`;
}

const tick = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
  mountDom();
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || function () {};
});

describe("基础导出（单源化）", () => {
  it("escapeHtml 由 admin-ui.js 单一导出", () => {
    expect(escapeHtml(`<b>"'&`)).toBe("&lt;b&gt;&quot;&#39;&amp;");
  });
  it("ifMatch 封装 If-Match 乐观锁头", () => {
    expect(ifMatch(7)).toEqual({ "If-Match": "7" });
  });
});

describe("admin-tagtree.js 知识点树", () => {
  const treeData = [
    { id: "s1", name: "C++基础", badge: "入门", children: [
      { id: "s1-t1", name: "数据结构", hint: "约 30%", children: [
        { id: "s1-t1-l1", num: "1.1.1", name: "数组", desc: "一维与二维数组" },
        { id: "s1-t1-l2", num: "1.1.2", name: "链表" },
      ] },
    ] },
  ];
  let committed;
  let kt;
  beforeEach(() => {
    committed = [];
    kt = createKnowledgeTree({
      els: {
        trigger: document.getElementById("ktTrigger"),
        hint: document.getElementById("ktHint"),
        pop: document.getElementById("ktPop"),
        filter: document.getElementById("ktFilter"),
        tree: document.getElementById("ktTree"),
        summary: document.getElementById("ktSummary"),
      },
      onChange: (ids) => { committed = ids; },
    });
    kt.setTree(treeData);
  });

  it("setTree 覆盖数据源", () => {
    expect(kt.getTreeData()).toBe(treeData);
  });
  it("open 展开浮层，点一级标题只展开不选择", () => {
    kt.open();
    expect(document.getElementById("ktPop").hidden).toBe(false);
    document.querySelector(".stage-head").click();
    expect(document.querySelector("li.kt-stage").classList.contains("open")).toBe(true);
    expect(committed).toEqual([]);
  });
  it("点三级行 = 选择，chips 与摘要同步", () => {
    kt.open();
    document.querySelector(".stage-head").click();
    document.querySelector(".group-head").click();
    const leaf = [...document.querySelectorAll("li.leaf")].find((li) => li.querySelector('[data-id="s1-t1-l2"]'));
    leaf.click();
    expect(committed).toEqual(["s1-t1-l2"]);
    expect(document.querySelectorAll("#ktTrigger .kt-chip")).toHaveLength(1);
    expect(document.getElementById("ktSummary").textContent).toContain("链表");
  });
  it("勾选不重绘整树：展开状态保持", () => {
    kt.open();
    document.querySelector(".stage-head").click();
    const stageLi = document.querySelector("li.kt-stage");
    const cb = stageLi.querySelector(".node-check");
    cb.checked = true;
    cb.dispatchEvent(new Event("change"));
    expect(stageLi.classList.contains("open")).toBe(true);
    expect(committed).toEqual(["s1"]);
  });
  it("二级节点可勾选为标签（不级联全选下级）", () => {
    kt.open();
    document.querySelector(".stage-head").click();
    const groupCb = document.querySelector('.node-check[data-id="s1-t1"]');
    groupCb.checked = true;
    groupCb.dispatchEvent(new Event("change"));
    expect(committed).toEqual(["s1-t1"]);
  });
  it("chip × 移除并同步树复选框（不重绘整树）", () => {
    kt.open();
    document.querySelector(".stage-head").click();
    document.querySelector(".group-head").click();
    [...document.querySelectorAll("li.leaf")].find((li) => li.querySelector('[data-id="s1-t1-l2"]')).click();
    document.querySelector('#ktTrigger .kt-chip button[data-id="s1-t1-l2"]').click();
    expect(committed).toEqual([]);
    expect(document.querySelector('.leaf-check[data-id="s1-t1-l2"]').checked).toBe(false);
  });
  it("过滤只显示匹配分支，无匹配给提示", () => {
    kt.open();
    document.querySelector(".stage-head").click();
    document.querySelector(".group-head").click();
    const filterInput = document.getElementById("ktFilter");
    filterInput.value = "数组";
    filterInput.dispatchEvent(new Event("input"));
    expect(document.querySelectorAll("#ktTree li.leaf")).toHaveLength(1);
    filterInput.value = "不存在";
    filterInput.dispatchEvent(new Event("input"));
    expect(document.getElementById("ktTree").textContent).toContain("无匹配知识点");
  });
  it("setSelected 把名称归一化为 id 并去重", () => {
    kt.setSelected(["数组", "s1-t1-l2", "不存在", "数组"]);
    expect(kt.getSelected()).toEqual(["s1-t1-l1", "s1-t1-l2"]);
  });
  it("ESC 只关浮层（capture 拦截）", () => {
    kt.open();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(document.getElementById("ktPop").hidden).toBe(true);
  });
});

describe("admin-ui.js 内联校验", () => {
  const SLOTS = [{ selectors: '[name="correctOption"]', slotId: "optionsError" }];
  it("区块级提示路由到 slot，字段级就地显示", () => {
    showFieldErrors(
      [
        { selector: '[name="correctOption"]', message: "请选择正确答案。" },
        { selector: "#f1", message: "请填写题干。" },
      ],
      SLOTS,
    );
    const slot = document.getElementById("optionsError");
    expect(slot.hidden).toBe(false);
    expect(slot.textContent).toContain("请选择正确答案");
    expect(document.querySelector('[name="correctOption"]').closest(".card").classList.contains("invalid-field")).toBe(true);
    const f1 = document.getElementById("f1");
    expect(f1.classList.contains("input-invalid")).toBe(true);
    expect(f1.nextElementSibling?.classList.contains("field-error")).toBe(true);
    expect(f1.closest("label").querySelector(".required-mark")).toBeTruthy();
  });
  it("clearFieldErrors 全量复位", () => {
    showFieldErrors([{ selector: "#f1", message: "请填写题干。" }], SLOTS);
    clearFieldErrors(SLOTS.map((r) => r.slotId));
    expect(document.getElementById("optionsError").hidden).toBe(true);
    expect(document.getElementById("f1").classList.contains("input-invalid")).toBe(false);
    expect(document.querySelector(".field-error")).toBeNull();
  });
});

describe("admin-list.js 分页列表", () => {
  const allItems = Array.from({ length: 45 }, (_, i) => ({ id: i + 1 }));
  let fetchCalls;
  let fail;
  let list;
  let itemTotal; // 主列表条数（决定页数）
  let extraTotal; // 钉在首页的附加行（只进「共 N 条」）
  beforeEach(() => {
    fetchCalls = [];
    fail = false;
    itemTotal = allItems.length;
    extraTotal = 0;
    list = createPagedList({
      els: {
        rows: document.getElementById("rows"),
        emptyTip: document.getElementById("emptyTip"),
        errorTip: document.getElementById("errorTip"),
        errorText: document.getElementById("errorText"),
        totalTip: document.getElementById("totalTip"),
        prevBtn: document.getElementById("prevBtn"),
        nextBtn: document.getElementById("nextBtn"),
        retryBtn: document.getElementById("retryBtn"),
        pageSizeSelect: document.getElementById("pageSizeSel"),
        checkAll: document.getElementById("checkAll"),
      },
      skeletonCols: 4,
      fetchPage: async ({ page, size }) => {
        fetchCalls.push([page, size]);
        await tick();
        if (fail) throw new Error("网络错误。");
        const pool = allItems.slice(0, itemTotal);
        return { items: pool.slice((page - 1) * size, page * size), total: pool.length, extra_total: extraTotal };
      },
      renderRows: (items) => {
        document.getElementById("rows").innerHTML = items.map((i) => `<tr><td>${i.id}</td></tr>`).join("");
      },
    });
  });

  it("首次加载显示骨架屏，完成后渲染首页", async () => {
    const loading = list.reload();
    expect(document.getElementById("rows").innerHTML).toContain("skeleton-line");
    await loading;
    expect(document.getElementById("rows").querySelectorAll("tr")).toHaveLength(20);
    expect(document.getElementById("totalTip").textContent).toBe("共 45 条 · 第 1/3 页");
    expect(document.getElementById("prevBtn").disabled).toBe(true);
    expect(document.getElementById("nextBtn").disabled).toBe(false);
  });
  it("下一页带正确参数", async () => {
    await list.reload();
    document.getElementById("nextBtn").click();
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchCalls.at(-1)).toEqual([2, 20]);
  });
  it("已有数据时刷新保留当前行，不叠骨架屏", async () => {
    await list.reload();
    const loading = list.reload();
    expect(document.getElementById("rows").innerHTML).not.toContain("skeleton-line");
    expect(document.getElementById("totalTip").textContent).toBe("正在加载…");
    await loading;
  });
  it("页大小切换回到第一页", async () => {
    await list.reload();
    const sel = document.getElementById("pageSizeSel");
    sel.value = "10";
    sel.dispatchEvent(new Event("change"));
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchCalls.at(-1)).toEqual([1, 10]);
  });
  it("错误态显示错误条并清空行，重试恢复", async () => {
    await list.reload();
    fail = true;
    await list.reload();
    expect(document.getElementById("errorTip").hidden).toBe(false);
    expect(document.getElementById("errorText").textContent).toBe("网络错误。");
    expect(document.getElementById("rows").querySelectorAll("tr")).toHaveLength(0);
    fail = false;
    document.getElementById("retryBtn").click();
    await new Promise((r) => setTimeout(r, 10));
    expect(document.getElementById("errorTip").hidden).toBe(true);
    expect(document.getElementById("rows").querySelectorAll("tr")).toHaveLength(20);
  });
  it("页码被钳到末页；retreatIfEmpty 末页删光后退页", async () => {
    await list.reload(); // totalCount 到位后钳制才按真实页数生效
    list.page = 99;
    await list.reload();
    expect(list.page).toBe(3);
  });
  it("extra_total 只计入「共 N 条」，不参与算页数", async () => {
    // 题库把 Scratch 挑战钉在第一页展示、不随翻页移动。把它算进 total 会多算出一页，
    // 翻过去请求的是越界 offset，只能看到空表（questions.html 的草稿区就栽在这上面）。
    itemTotal = 40; // 整两页
    extraTotal = 3;
    await list.reload();
    expect(document.getElementById("totalTip").textContent).toBe("共 43 条 · 第 1/2 页");
    list.page = 99;
    await list.reload();
    expect(list.page).toBe(2);
    expect(document.getElementById("nextBtn").disabled).toBe(true);
  });
  it("skeletonRows 导出可用", () => {
    expect(skeletonRows(4)).toContain("skeleton-line");
  });
});


describe("admin-markdown.js 空位标记（与后端 BLANK_KEY_RE 对齐）", () => {
  // 后端 schemas.py 的 BLANK_KEY_RE 容忍空白和非空花括号；前端只认严格形态时，
  // 这些写法存得进库、过得了校验，却原样渲染到学生卷上——花括号里写的往往就是答案。
  it("placeholder 的四种写法全部替换，data-key 提取不受空白影响", () => {
    for (const raw of ["\\placeholder[port]{}", "\\placeholder[port]{80}", "\\placeholder[ port ]{}", "\\placeholder[port] {}"]) {
      const out = markBlanksInHtml(`<p>${raw}</p>`);
      expect(out, `${raw} 必须被替换`).toContain('class="blank-mark"');
      expect(out, `${raw} 的 key 必须是 port`).toContain('data-key="port"');
      expect(out).not.toContain("placeholder");
    }
  });

  it("花括号里的内容（往往是答案）绝不能留在产物里", () => {
    const out = markBlanksInHtml("<p>默认端口是 \\placeholder[port]{80}。</p>");
    expect(out).not.toContain("{80}");
    expect(out).not.toContain("80");
  });

  it("<pre>/<code> 内的内容不替换（代码不能被误显示成空位）", () => {
    const code = "\\placeholder[port]{80}";
    expect(markBlanksInHtml(`<pre>${code}</pre>`)).toContain(code);
    expect(markBlanksInHtml(`<code>${code}</code>`)).toContain(code);
  });

  it("___ 与 {{blank}} 两种旧写法仍然替换", () => {
    expect(markBlanksInHtml("<p>____</p>")).toContain('class="blank-mark"');
    expect(markBlanksInHtml("<p>{{blank}}</p>")).toContain('class="blank-mark"');
  });
});
