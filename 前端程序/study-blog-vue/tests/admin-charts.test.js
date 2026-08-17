// @vitest-environment jsdom
// 成绩分析图表（admin-charts.js）的护栏。
//
// 这里盯的不是像素——jsdom 没有排版，量出来的几何是假的（浏览器里已经手验过一轮：
// 参考线标签不再相撞、窄容器不溢出、提示框贴边翻转）。这里盯的是**编码判断**：
// 哪个得分率算"低"、什么情况打哪个徽标、样本不足时会不会照画不误。
// 这些阈值是有理由的，而它们看起来最像"可以顺手清理掉的魔数"。
import { beforeEach, describe, expect, it } from "vitest";
import {
  emptyState,
  renderDiscrimination,
  renderDistribution,
  renderDurationScatter,
  renderItemRates,
  renderScoreStrip,
} from "../public/admin/admin-charts.js";

let host;
beforeEach(() => {
  document.body.innerHTML = '<div id="host"></div>';
  host = document.getElementById("host");
});

const item = (over = {}) => ({
  sort_order: 1, problem_id_no: "P1", type: "choice", title: "题目", full_score: 10,
  answered: 20, judge_failed: 0, score_rate: 0.8, high_rate: 0.9, low_rate: 0.5,
  discrimination: 0.4, suspect: null, missing: false, ...over,
});

describe("逐题得分率：强调而非分类", () => {
  it("按得分率分三档，且只有需要老师看的那两档换色", () => {
    renderItemRates(host, {
      items: [
        item({ sort_order: 1, score_rate: 0.8 }),   // 常态
        item({ sort_order: 2, score_rate: 0.54 }),  // < 0.55 偏低
        item({ sort_order: 3, score_rate: 0.39 }),  // < 0.4 严重
      ],
    });
    const fills = [...host.querySelectorAll(".item-fill")].map((el) => el.className);
    expect(fills).toEqual(["item-fill", "item-fill is-low", "item-fill is-crit"]);
  });

  it("得分率为空（没人作答）不当成 0 分，也不染色", () => {
    renderItemRates(host, { items: [item({ score_rate: null, answered: 0 })] });
    expect(host.querySelector(".item-fill").className).toBe("item-fill");
    expect(host.querySelector(".item-pct").textContent).toBe("—");
  });

  it("质检徽标带文字，不靠颜色单独承载", () => {
    // 红绿在这套令牌下 CVD ΔE 只有 5.2，色盲用户看到的是同一个颜色——
    // 徽标一旦退化成纯色块，这三种情况对他们就完全消失了
    renderItemRates(host, {
      items: [
        item({ sort_order: 1, suspect: "negative_discrimination" }),
        item({ sort_order: 2, suspect: "all_low" }),
        item({ sort_order: 3, judge_failed: 3 }),
      ],
    });
    const badges = [...host.querySelectorAll(".chart-badge")].map((el) => el.textContent);
    expect(badges).toEqual(["疑似答案配错", "全员偏低", "判题异常 3 人"]);
  });

  it("按卷内顺序渲染，不按得分率重排", () => {
    // 讲评是顺着卷子走的；排序会让老师每讲一道题都要重新找位置
    renderItemRates(host, {
      items: [item({ sort_order: 1, score_rate: 0.2 }), item({ sort_order: 2, score_rate: 0.9 })],
    });
    expect([...host.querySelectorAll(".item-no")].map((el) => el.textContent)).toEqual(["1", "2"]);
  });
});

describe("题目诊断：哑铃图", () => {
  const grouping = { enabled: true, group_size: 6, participants: 24, min_participants: 8 };

  it("区分度为负的那行要显眼——那多半是答案配错了", () => {
    renderDiscrimination(host, {
      items: [item({ sort_order: 1, high_rate: 0.2, low_rate: 0.7, discrimination: -0.5 })],
      grouping,
    });
    expect(host.querySelectorAll(".dumbbell-link.is-bad")).toHaveLength(1);
    const value = host.querySelector(".dumbbell-value");
    expect(value.textContent).toBe("↓50%");
    expect(value.getAttribute("class")).toContain("is-bad");
  });

  it("两端都直接标数值——低端颜色对白底的对比度不够，不能让它单独承载信息", () => {
    renderDiscrimination(host, { items: [item()], grouping });
    expect(host.querySelector(".dumbbell-value").textContent).toBe("+40%");
    expect(host.querySelectorAll(".dumbbell-dot.is-low")).toHaveLength(1);
    expect(host.querySelectorAll(".dumbbell-dot.is-high")).toHaveLength(1);
    // 图例把分组口径写在脸上，省得有人拿它跟"参考人数"对不上
    expect(host.querySelector(".chart-legend").textContent).toContain("27%");
  });

  it("没有分组数据的题目直接走空态，不画半张图", () => {
    renderDiscrimination(host, {
      items: [item({ high_rate: null, low_rate: null, discrimination: null })],
      grouping,
    });
    expect(host.querySelector(".chart-empty")).not.toBeNull();
    expect(host.querySelector("svg")).toBeNull();
  });
});

describe("分数分布", () => {
  const dist = [{ range: "0–50", count: 2 }, { range: "50–100", count: 6 }];

  it("十个桶同一个颜色，及格与否交给背景分区", () => {
    // 染成红绿会被读成两个 series；及格不是一个类别，是一条线的两侧
    renderDistribution(host, {
      distribution: dist, fullScore: 100, passScore: 60, avg: 58, participants: 8,
    });
    const bars = [...host.querySelectorAll(".chart-bar")];
    expect(bars).toHaveLength(2);
    expect(new Set(bars.map((b) => b.getAttribute("class")))).toEqual(new Set(["chart-bar"]));
    expect(host.querySelectorAll(".chart-band-pass")).toHaveLength(1);
    expect(host.querySelectorAll(".chart-band-fail")).toHaveLength(1);
  });

  it("不设及格线的卷不画参考线，也不画分区", () => {
    renderDistribution(host, {
      distribution: dist, fullScore: 100, passScore: null, avg: null, participants: 8,
    });
    expect(host.querySelectorAll(".chart-ref")).toHaveLength(0);
    expect(host.querySelectorAll(".chart-band-pass, .chart-band-fail")).toHaveLength(0);
    expect(host.querySelectorAll(".chart-bar")).toHaveLength(2);
  });

  it("空桶不画柱子也不标 0", () => {
    renderDistribution(host, {
      distribution: [{ range: "0–50", count: 0 }, { range: "50–100", count: 3 }],
      fullScore: 100, passScore: 60, avg: 70, participants: 3,
    });
    expect(host.querySelectorAll(".chart-bar")).toHaveLength(1);
    expect([...host.querySelectorAll(".chart-bar-label")].map((t) => t.textContent)).toEqual(["3"]);
  });

  it("x 轴标签密度跟着桶数走，且总能读到满分", () => {
    // 桶数是后端按人数算的（4–10 个）。按 10 桶写死"隔一个标一次"，4 桶时轴上
    // 只会剩两个标签、读不出刻度——这是改成自适应分桶后必然撞上的问题。
    const axisTexts = (bins) => {
      renderDistribution(host, {
        distribution: Array.from({ length: bins }, (_, i) => ({ range: `${i}`, count: 1 })),
        fullScore: 100, passScore: 60, avg: 58, participants: 20,
      });
      return [...host.querySelectorAll(".chart-axis")]
        .filter((t) => t.getAttribute("text-anchor") === "middle")
        .map((t) => t.textContent);
    };
    expect(axisTexts(4)).toEqual(["0", "25", "50", "75", "100"]);
    expect(axisTexts(10)).toEqual(["0", "20", "40", "60", "80", "100"]);
  });

  it("及格线与平均线的标签不放在同一行——两者常常只差几分", () => {
    renderDistribution(host, {
      distribution: dist, fullScore: 100, passScore: 60, avg: 58, participants: 8,
    });
    const ys = [...host.querySelectorAll(".chart-ref-label")].map((t) => t.getAttribute("y"));
    expect(new Set(ys).size).toBe(2);
  });
});

describe("用时 × 分数散点", () => {
  const points = [
    { name: "甲", score: 80, minutes: 40, submitKind: "manual" },
    { name: "乙", score: 30, minutes: 90, submitKind: "auto" },
  ];

  it("异常点用形状二次编码，不只靠颜色", () => {
    renderDurationScatter(host, {
      points, fullScore: 100, passScore: 60, durationMinutes: 90,
    });
    expect(host.querySelectorAll("circle.dot")).toHaveLength(1);
    expect(host.querySelectorAll("path.dot.is-auto")).toHaveLength(1);
  });

  it("限时卷用配置时长定标尺，不用实际最大用时", () => {
    // 按后者定标尺，"几乎所有人都用满了"会看起来像"大家都很宽裕"
    renderDurationScatter(host, {
      points: [{ name: "甲", score: 80, minutes: 20, submitKind: "manual" }],
      fullScore: 100, passScore: 60, durationMinutes: 90,
    });
    expect(host.querySelector(".chart-legend")).not.toBeNull();
    const labels = [...host.querySelectorAll(".chart-ref-label")].map((t) => t.textContent);
    expect(labels).toContain("限时 90m");
  });

  it("没有用时数据时走空态", () => {
    renderDurationScatter(host, {
      points: [{ name: "甲", score: 80, minutes: null }], fullScore: 100, passScore: 60,
      durationMinutes: null,
    });
    expect(host.querySelector(".chart-empty")).not.toBeNull();
  });
});

describe("点带图：人少时替代直方图", () => {
  const strip = (points, over = {}) =>
    renderScoreStrip(host, { points, fullScore: 100, passScore: 60, avg: 55, ...over });

  it("一人一个点，不做任何分箱", () => {
    // 「样本过少暂不展示」对老师是个坏答复——他手上明明有 8 个真实成绩想看
    strip([
      { name: "甲", score: 30 }, { name: "乙", score: 55 }, { name: "丙", score: 88 },
    ]);
    expect(host.querySelectorAll("circle.dot")).toHaveLength(3);
    expect(host.querySelector(".chart-empty")).toBeNull();
    expect(host.querySelector(".chart-legend").textContent).toContain("3 人");
  });

  it("同分的人向上堆叠，堆多高画布就有多高", () => {
    // 随机抖动会让"有几个人同分"读不出来，而这正是小班里老师最想知道的
    strip([1, 2, 3, 4].map((i) => ({ name: `学员${i}`, score: 70 })));
    const cys = [...host.querySelectorAll("circle.dot")].map((c) => Number(c.getAttribute("cy")));
    expect(new Set(cys).size).toBe(4);                  // 四个不同的高度，没有重叠
    const cxs = [...host.querySelectorAll("circle.dot")].map((c) => c.getAttribute("cx"));
    expect(new Set(cxs).size).toBe(1);                  // 同分 → 同一个横坐标
    const [, , , height] = host.querySelector("svg").getAttribute("viewBox").split(" ").map(Number);
    expect(Math.min(...cys)).toBeGreaterThan(0);        // 最高那个没顶出画布
    expect(Math.max(...cys)).toBeLessThan(height);
  });

  it("及格线与平均线照画，且不放同一行", () => {
    strip([{ name: "甲", score: 30 }]);
    const labels = [...host.querySelectorAll(".chart-ref-label")];
    expect(labels.map((t) => t.textContent)).toEqual(["及格 60", "均 55"]);
    expect(new Set(labels.map((t) => t.getAttribute("y"))).size).toBe(2);
  });

  it("没人交卷才是真的空态", () => {
    strip([{ name: "甲", score: null }]);
    expect(host.querySelector(".chart-empty")).not.toBeNull();
  });
});

describe("空态", () => {
  it("用 textContent 填充，不给注入留口子", () => {
    emptyState(host, '<img src=x onerror="alert(1)">');
    expect(host.querySelector("img")).toBeNull();
    expect(host.querySelector(".chart-empty").textContent).toContain("onerror");
  });
});
