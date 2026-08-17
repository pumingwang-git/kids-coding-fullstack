// 后台图表：零依赖手绘 SVG。
//
// 为什么不引 ECharts/Chart.js：后台是纯 HTML 逐页接 API，全部依赖走 vendor/ 本地化
// （见 vendor/README.md）。为四张图引一个 300KB+ 的库，还要再给它配一套主题去贴合
// 纸白/深绿的令牌，成本高于自己画——这四张图用到的几何就是矩形、线、圆。
//
// **颜色一律走 CSS 类，不写 fill 属性**：调色板留在 admin.css 一处，
// 换主题不用回来改 JS。SVG 元素同样吃 class。
//
// 配色的取舍（用 dataviz 的校验器算过，不是拍脑袋）：
//   - 页面既有的 --accent(#2f806e) 与 --danger(#b95c50) **不能当成对的分类色用**：
//     protan 下 ΔE 只有 5.2，红绿色盲看来是同一个颜色。所以这里一处成对分类色都没有——
//     分数分布是单色相、逐题得分率与散点是"强调 + 灰"、哑铃是同色相两档。
//   - 哑铃两端 --chart-low(#6faa99) / --chart-high(#255f52)：CVD ΔE 24.9 通过。
//     低端对白底对比度 2.66 偏低，靠两端都直接标数值兜底，不靠颜色单独承载信息。

const NS = "http://www.w3.org/2000/svg";

export function svgEl(tag, attrs = {}, parent = null) {
  const el = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  if (parent) parent.appendChild(el);
  return el;
}

// ==================== 悬浮提示 ====================
// 全页一个，挂在 body 上。挂在图表容器里会被 .card 的 overflow 裁掉，
// 而且四张图各自一个提示框，切换视图时容易漏关一个留在屏幕上。
let tipEl = null;

function tooltip() {
  if (!tipEl) {
    tipEl = document.createElement("div");
    tipEl.className = "chart-tip";
    tipEl.hidden = true;
    document.body.appendChild(tipEl);
  }
  return tipEl;
}

export function showTip(html, x, y) {
  const el = tooltip();
  el.innerHTML = html;
  el.hidden = false;
  const pad = 14;
  const rect = el.getBoundingClientRect();
  // 贴边时翻到另一侧，否则提示框会被视口切掉一半
  const left = x + pad + rect.width > window.innerWidth - 8 ? x - rect.width - pad : x + pad;
  const top = y + pad + rect.height > window.innerHeight - 8 ? y - rect.height - pad : y + pad;
  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
}

export function hideTip() {
  if (tipEl) tipEl.hidden = true;
}

const tipRow = (key, value) => `<div class="tt-row"><span>${key}</span><b>${value}</b></div>`;

/** 给任意元素挂上「移入显示、移出隐藏」。返回的元素便于链式使用。 */
function bindTip(el, htmlFn) {
  el.addEventListener("mousemove", (event) => showTip(htmlFn(), event.clientX, event.clientY));
  el.addEventListener("mouseleave", hideTip);
  return el;
}

/** 空态。样本太少时画出来的图比不画危害大——读者不会自己给统计量打折扣。 */
export function emptyState(host, text) {
  host.innerHTML = "";
  const box = document.createElement("div");
  box.className = "chart-empty";
  box.textContent = text;
  host.appendChild(box);
}

const pct = (value) => `${Math.round(value * 100)}%`;

// ==================== 视图一 · 分数分布 ====================
/**
 * 纵向直方图 + 及格线 + 平均线。
 *
 * 三处与旧实现（横向 div 条）不同，都是有意的：
 *   1. 纵向：分数是有序量，读者对"低分→高分"的空间直觉是左→右，把有序轴放到纵向读着别扭；
 *   2. 十个桶**同一个颜色**：及格与不及格不是两个 series，染成红绿会被读成两类。
 *      及格与否交给背景分区表达；
 *   3. viewBox + width:100%：旧实现把条宽写死成 320px，窄屏和宽屏一个样。
 */
export function renderDistribution(host, { distribution, fullScore, passScore, avg, participants }) {
  host.innerHTML = "";
  const W = 620, H = 250, padL = 36, padR = 12, padT = 26, padB = 32;
  const iw = W - padL - padR, ih = H - padT - padB;
  const counts = distribution.map((b) => b.count);
  const maxCount = Math.max(...counts, 1);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
                             "aria-label": "分数分布直方图" });
  const X = (score) => padL + (score / fullScore) * iw;
  const barW = iw / distribution.length;
  const labelEvery = distribution.length > 6 ? 2 : 1;

  // 及格 / 不及格底色。pass_score 为空的卷（不设及格线）就不分区。
  if (passScore != null && fullScore > 0) {
    const passX = X(passScore);
    svgEl("rect", { x: padL, y: padT, width: Math.max(passX - padL, 0), height: ih,
                    class: "chart-band-fail" }, svg);
    svgEl("rect", { x: passX, y: padT, width: Math.max(padL + iw - passX, 0), height: ih,
                    class: "chart-band-pass" }, svg);
  }

  // 横向网格：刻度取整，人数少时不要画出 0.5 个人这种刻度
  const step = Math.max(1, Math.ceil(maxCount / 4));
  for (let v = 0; v <= maxCount; v += step) {
    const y = padT + ih - (v / maxCount) * ih;
    svgEl("line", { x1: padL, y1: y, x2: padL + iw, y2: y, class: "chart-grid" }, svg);
    svgEl("text", { x: padL - 6, y: y + 3, class: "chart-axis", "text-anchor": "end" }, svg)
      .textContent = v;
  }

  distribution.forEach((bucket, i) => {
    const h = (bucket.count / maxCount) * ih;
    const x = padL + i * barW + barW * 0.16;
    const y = padT + ih - h;
    if (bucket.count > 0) {
      bindTip(
        svgEl("rect", { x, y, width: barW * 0.68, height: h, rx: 3, class: "chart-bar" }, svg),
        () => `<div class="tt-title">${bucket.range} 分</div>` +
              tipRow("人数", `${bucket.count} 人`) +
              tipRow("占比", participants ? pct(bucket.count / participants) : "—"),
      );
      // 数值直接标在柱顶：一眼能读到具体人数，不必悬浮
      svgEl("text", { x: x + barW * 0.34, y: y - 5, class: "chart-bar-label",
                      "text-anchor": "middle" }, svg).textContent = bucket.count;
    }
    // x 轴标桶的起点。**标签密度跟着桶数走**：桶数是按人数算的（后端 _distribution_bins，
    // 4–10 个），按 10 桶写死"隔一个标一次"的话，4 桶时只会剩下两个标签、轴读不出来。
    if (i % labelEvery === 0) {
      svgEl("text", { x: padL + i * barW, y: H - padB + 14, class: "chart-axis",
                      "text-anchor": "middle" }, svg)
        .textContent = Math.round((i * fullScore) / distribution.length);
    }
  });
  // 右端点单独补一个：不标的话读者不知道最后一个桶到哪结束，轴读不到满分
  svgEl("text", { x: padL + iw, y: H - padB + 14, class: "chart-axis",
                  "text-anchor": "middle" }, svg).textContent = fullScore;

  // 及格线标在图上方居中，平均线标在图**内部**——两者常常只差几分（这份数据是 60 与 58），
  // 都放顶上必然叠在一起。这不是假想的边角情况：平均分贴着及格线正是最常见的一场考试。
  refLineV(svg, { x: X(passScore), padT, ih, label: `及格 ${passScore}`,
                  cls: "is-pass", show: passScore != null });
  refLineV(svg, { x: X(avg), padT, ih, label: `均 ${avg}`, show: avg != null,
                  inside: true, flip: X(avg) > padL + iw * 0.82 });
  host.appendChild(svg);
}

/**
 * 人太少时替代直方图的**点带图**：一人一个点排在分数轴上，叠及格线与平均线。
 *
 * 为什么不是"样本过少，暂不展示"：那对老师是个坏答复——他手上明明有 8 个真实成绩想看。
 * 直方图在这个规模下才是真的不能画（10 个桶要 ~100 个样本，8 个人摊进去是一把梳子），
 * 但逐点画不需要任何分箱假设，8 个点比任何直方图都清楚。
 *
 * 同分的点向上堆叠而不是随机抖动：抖动会让"有几个人同分"变得读不出来，
 * 而这恰好是小班里老师最想知道的事。
 */
export function renderScoreStrip(host, { points, fullScore, passScore, avg }) {
  host.innerHTML = "";
  const usable = points.filter((p) => p.score != null).sort((a, b) => a.score - b.score);
  if (!usable.length) {
    emptyState(host, "还没有人交卷。");
    return;
  }
  const W = 620, padL = 36, padR = 12, padT = 26, padB = 30;
  const iw = W - padL - padR;
  const X = (score) => padL + (fullScore > 0 ? score / fullScore : 0) * iw;
  const R = 6, GAP = 3;

  // 先算堆叠层数，再定画布高度——否则堆得最高的那一摞会顶出画布
  let previousX = -Infinity;
  let level = 0;
  const placed = usable.map((point) => {
    const x = X(point.score);
    level = x - previousX < R * 2 ? level + 1 : 0;
    previousX = x;
    return { point, x, level };
  });
  const levels = Math.max(...placed.map((p) => p.level)) + 1;
  const ih = Math.max(60, levels * (R * 2 + GAP) + 10);
  const H = padT + padB + ih;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
                             "aria-label": "每位学员的分数" });

  if (passScore != null && fullScore > 0) {
    const passX = X(passScore);
    svgEl("rect", { x: padL, y: padT, width: Math.max(passX - padL, 0), height: ih,
                    class: "chart-band-fail" }, svg);
    svgEl("rect", { x: passX, y: padT, width: Math.max(padL + iw - passX, 0), height: ih,
                    class: "chart-band-pass" }, svg);
  }
  svgEl("line", { x1: padL, y1: padT + ih, x2: padL + iw, y2: padT + ih, class: "chart-grid" }, svg);
  for (let i = 0; i <= 4; i += 1) {
    const score = (fullScore / 4) * i;
    svgEl("text", { x: X(score), y: H - padB + 16, class: "chart-axis",
                    "text-anchor": "middle" }, svg).textContent = Math.round(score);
  }

  for (const { point, x, level: lv } of placed) {
    const y = padT + ih - R - lv * (R * 2 + GAP);
    bindTip(
      svgEl("circle", { cx: x, cy: y, r: R - 1.5, class: "dot" }, svg),
      () => `<div class="tt-title">${escapeText(point.name)}</div>` +
            tipRow("得分", `${point.score} / ${fullScore}`) +
            (passScore != null ? tipRow("及格线", passScore) : ""),
    );
  }

  refLineV(svg, { x: X(passScore), padT, ih, label: `及格 ${passScore}`,
                  cls: "is-pass", show: passScore != null });
  refLineV(svg, { x: X(avg), padT, ih, label: `均 ${avg}`, show: avg != null,
                  inside: true, flip: X(avg) > padL + iw * 0.82 });
  host.appendChild(svg);

  const note = document.createElement("div");
  note.className = "chart-legend";
  note.innerHTML = `<span class="chart-legend-note">已交卷 ${usable.length} 人，`
    + "不足以画分布形状，这里逐个列出每位学员的分数。</span>";
  host.appendChild(note);
}

/**
 * 竖直参考线 + 标签。show 为假时什么都不画（不设及格线的卷、没人交卷的场）。
 * inside=true 把标签放进绘图区顶部；flip 在贴近右边界时把它翻到线的左侧，否则会出画布。
 */
function refLineV(svg, { x, padT, ih, label, cls = "", show, inside = false, flip = false }) {
  if (!show || !Number.isFinite(x)) return;
  svgEl("line", { x1: x, y1: padT - 4, x2: x, y2: padT + ih, class: `chart-ref ${cls}` }, svg);
  const attrs = inside
    ? { x: flip ? x - 4 : x + 4, y: padT + 11, "text-anchor": flip ? "end" : "start" }
    : { x, y: padT - 9, "text-anchor": "middle" };
  svgEl("text", { ...attrs, class: `chart-ref-label ${cls}` }, svg).textContent = label;
}

// ==================== 视图二 · 逐题得分率 ====================
/**
 * 一题一行的横条。**按卷内顺序排，不按得分率排序**——老师是按卷子顺序讲评的，
 * 排序会让他每讲一道题都要重新找位置。
 *
 * 配色是"强调 + 灰"而不是红黄绿三档：三种颜色会被读成三个类别，而这里的故事是
 * "哪几道要讲"，那是强调。低于阈值的用状态色并**带文字标签**，不靠颜色单独承载。
 */
export function renderItemRates(host, { items }) {
  host.innerHTML = "";
  const list = document.createElement("div");
  list.className = "item-list";
  for (const item of items) {
    const rate = item.score_rate;
    const row = document.createElement("div");
    row.className = "item-row";
    const badges = [
      item.suspect === "negative_discrimination"
        ? '<span class="chart-badge is-bad">疑似答案配错</span>' : "",
      item.suspect === "all_low" ? '<span class="chart-badge is-warn">全员偏低</span>' : "",
      item.judge_failed > 0
        ? `<span class="chart-badge is-bad">判题异常 ${item.judge_failed} 人</span>` : "",
      item.missing ? '<span class="chart-badge is-warn">题已删除</span>' : "",
    ].join("");
    const tone = rate == null ? "" : rate < 0.4 ? " is-crit" : rate < 0.55 ? " is-low" : "";
    row.innerHTML = `
      <div class="item-meta">
        <span class="item-no">${item.sort_order}</span>
        <span class="item-tag">${TYPE_LABEL[item.type] || "—"}</span>
      </div>
      <div class="item-track">
        <div class="item-fill${tone}" style="width:${rate == null ? 0 : Math.round(rate * 100)}%"></div>
      </div>
      <div class="item-pct">${rate == null ? "—" : pct(rate)}</div>
      <div class="item-sub">${escapeText(item.title) || item.problem_id_no} · 满分 ${item.full_score}${badges}</div>`;
    bindTip(row, () =>
      `<div class="tt-title">第 ${item.sort_order} 题 · ${TYPE_LABEL[item.type] || "—"}</div>` +
      tipRow("得分率", rate == null ? "—" : pct(rate)) +
      tipRow("计入人数", `${item.answered} 人`) +
      (item.discrimination != null ? tipRow("区分度", item.discrimination.toFixed(2)) : "") +
      (item.judge_failed ? tipRow("判题异常", `${item.judge_failed} 人（不计入）`) : ""));
    list.appendChild(row);
  }
  host.appendChild(list);
}

const TYPE_LABEL = {
  choice: "单选", multi_choice: "多选", judge: "判断", fill: "填空", programming: "操作",
};

function escapeText(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

// ==================== 视图三 · 题目诊断（高分组 vs 低分组） ====================
/**
 * 哑铃图：一题一行，两个点分别是高分组、低分组的得分率，连线长度就是区分度。
 *
 * 为什么是哑铃不是分组柱状：读者要读的是**两点之间的距离**，柱状图里这个距离
 * 得靠比较两根柱子的高度差在心里算，哑铃直接把它画成了一条线的长度。
 *
 * 同色相两档 + 两端都直接标数值：颜色只是辅助，看不出深浅也能从数字读出谁高谁低。
 */
export function renderDiscrimination(host, { items, grouping }) {
  host.innerHTML = "";
  const usable = items.filter((i) => i.high_rate != null && i.low_rate != null);
  if (!usable.length) {
    emptyState(host, "暂无可对比的题目。");
    return;
  }
  const rowH = 26, padL = 34, padR = 46, padT = 26, padB = 8;
  const W = 620, H = padT + padB + usable.length * rowH;
  const iw = W - padL - padR;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
                             "aria-label": "高低分组得分率对比" });
  const X = (rate) => padL + rate * iw;

  // 顶部刻度：0 / 50% / 100%
  for (const t of [0, 0.5, 1]) {
    svgEl("line", { x1: X(t), y1: padT - 6, x2: X(t), y2: H - padB, class: "chart-grid" }, svg);
    svgEl("text", { x: X(t), y: padT - 12, class: "chart-axis", "text-anchor": "middle" }, svg)
      .textContent = pct(t);
  }

  usable.forEach((item, i) => {
    const y = padT + i * rowH + rowH / 2;
    const negative = item.discrimination < 0;
    svgEl("text", { x: padL - 8, y: y + 4, class: "chart-axis", "text-anchor": "end" }, svg)
      .textContent = item.sort_order;
    svgEl("line", { x1: X(item.low_rate), y1: y, x2: X(item.high_rate), y2: y,
                    class: `dumbbell-link${negative ? " is-bad" : ""}` }, svg);
    svgEl("circle", { cx: X(item.low_rate), cy: y, r: 5, class: "dumbbell-dot is-low" }, svg);
    svgEl("circle", { cx: X(item.high_rate), cy: y, r: 5, class: "dumbbell-dot is-high" }, svg);
    // 直接标数值：低端颜色对白底的对比度不够，不能让它单独承载信息
    const right = Math.max(item.low_rate, item.high_rate);
    svgEl("text", { x: X(right) + 8, y: y + 4,
                    class: `dumbbell-value${negative ? " is-bad" : ""}` }, svg)
      .textContent = negative ? `↓${pct(Math.abs(item.discrimination))}` : `+${pct(item.discrimination)}`;
    bindTip(
      svgEl("rect", { x: padL, y: y - rowH / 2, width: iw + padR, height: rowH,
                      class: "dumbbell-hit" }, svg),
      () => `<div class="tt-title">第 ${item.sort_order} 题 · ${escapeText(item.title)}</div>` +
            tipRow("高分组得分率", pct(item.high_rate)) +
            tipRow("低分组得分率", pct(item.low_rate)) +
            tipRow("区分度", item.discrimination.toFixed(2)) +
            (negative
              ? '<div class="tt-warn">低分组反而更高，多半是答案配错了</div>'
              : item.discrimination < 0.2
                ? '<div class="tt-warn">区分度偏低，这道题分不出水平</div>' : ""));
  });

  host.appendChild(svg);
  const legend = document.createElement("div");
  legend.className = "chart-legend";
  legend.innerHTML =
    `<span><i class="dot-low"></i>低分组（后 ${grouping.group_size} 人）</span>` +
    `<span><i class="dot-high"></i>高分组（前 ${grouping.group_size} 人）</span>` +
    `<span class="chart-legend-note">按总分前 / 后 27% 分组</span>`;
  host.appendChild(legend);
}

// ==================== 视图四 · 用时 × 分数 ====================
/**
 * 散点。同样是"强调 + 灰"：普通点中性，**异常点**才有颜色，且用形状二次编码
 * （超时自动交卷画三角），不让颜色单独承载信息。
 *
 * 老师从这张图里捞的是左下角那一簇——早早交卷且分低，那是放弃的人，
 * 比"分数最低的那个"有用得多（最低分那个他本来就知道）。
 */
export function renderDurationScatter(host, { points, fullScore, passScore, durationMinutes }) {
  host.innerHTML = "";
  const usable = points.filter((p) => p.minutes != null && p.score != null);
  if (!usable.length) {
    emptyState(host, "没有可用的用时数据。");
    return;
  }
  const W = 620, H = 260, padL = 36, padR = 14, padT = 16, padB = 30;
  const iw = W - padL - padR, ih = H - padT - padB;
  // 限时卷用配置的时长当上界，不限时的用实际最大用时——按后者给限时卷定标尺，
  // 会让"几乎所有人都用满了"看起来像"大家都很宽裕"。
  const xMax = Math.max(durationMinutes || 0, ...usable.map((p) => p.minutes), 1);
  const yMax = Math.max(fullScore, 1);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
                             "aria-label": "用时与分数散点图" });
  const X = (m) => padL + (m / xMax) * iw;
  const Y = (s) => padT + ih - (s / yMax) * ih;

  for (let i = 0; i <= 4; i += 1) {
    const score = (yMax / 4) * i;
    svgEl("line", { x1: padL, y1: Y(score), x2: padL + iw, y2: Y(score), class: "chart-grid" }, svg);
    svgEl("text", { x: padL - 6, y: Y(score) + 3, class: "chart-axis", "text-anchor": "end" }, svg)
      .textContent = Math.round(score);
  }
  for (let i = 0; i <= 3; i += 1) {
    const m = (xMax / 3) * i;
    svgEl("text", { x: X(m), y: H - padB + 14, class: "chart-axis", "text-anchor": "middle" }, svg)
      .textContent = `${Math.round(m)}m`;
  }

  if (passScore != null) {
    svgEl("line", { x1: padL, y1: Y(passScore), x2: padL + iw, y2: Y(passScore),
                    class: "chart-ref is-pass" }, svg);
    svgEl("text", { x: padL + iw - 4, y: Y(passScore) - 5,
                    class: "chart-ref-label is-pass", "text-anchor": "end" }, svg)
      .textContent = `及格 ${passScore}`;
  }
  if (durationMinutes) {
    svgEl("line", { x1: X(durationMinutes), y1: padT, x2: X(durationMinutes), y2: padT + ih,
                    class: "chart-ref" }, svg);
    svgEl("text", { x: X(durationMinutes) - 4, y: padT + 10,
                    class: "chart-ref-label", "text-anchor": "end" }, svg)
      .textContent = `限时 ${durationMinutes}m`;
  }

  for (const point of usable) {
    const auto = point.submitKind === "auto";
    const x = X(point.minutes), y = Y(point.score);
    const node = auto
      ? svgEl("path", { d: `M ${x} ${y - 4.6} L ${x + 4} ${y + 3.2} L ${x - 4} ${y + 3.2} Z`,
                        class: "dot is-auto" }, svg)
      : svgEl("circle", { cx: x, cy: y, r: 3.6, class: "dot" }, svg);
    bindTip(node, () =>
      `<div class="tt-title">${escapeText(point.name)}</div>` +
      tipRow("得分", `${point.score} / ${fullScore}`) +
      tipRow("用时", `${point.minutes} 分钟`) +
      tipRow("交卷", auto ? "超时自动" : "手动"));
  }

  host.appendChild(svg);
  const legend = document.createElement("div");
  legend.className = "chart-legend";
  legend.innerHTML =
    '<span><i class="dot-normal"></i>手动交卷</span>' +
    '<span><i class="dot-auto"></i>超时自动交卷</span>' +
    '<span class="chart-legend-note">左下角聚集 = 早早交卷且分低，多半是放弃</span>';
  host.appendChild(legend);
}
