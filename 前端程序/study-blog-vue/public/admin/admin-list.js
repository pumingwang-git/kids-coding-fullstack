// 后台列表页通用组件：idle/loading/error 三态 + 骨架屏 + 分页器。
// 从 questions.html 抽出，试卷列表与组卷 Modal 的选题面板（papers.js）复用。
// 页面只负责：筛选参数（fetchPage）、行 HTML（renderRows）、页面级收尾（afterRender）。

export function skeletonRows(colCount, rowCount = 5) {
  const cell = '<td><div class="skeleton-line"></div></td>';
  return Array.from({ length: rowCount }, () => `<tr>${cell.repeat(colCount)}</tr>`).join("");
}

/**
 * 受控分页列表。三态语义：
 * - loading 且已有数据：保留当前行不闪烁（避免切换分区时骨架屏叠加跳动）；
 * - loading 且无数据：骨架屏；
 * - error：清空行、显示错误条，retryBtn 触发 reload。
 *
 * fetchPage 返回的 `total` 决定页数，`extra_total`（可选）只计入「共 N 条」不参与翻页：
 * 给的是「钉在第一页、不随翻页移动的附加行」——题库把 Scratch 挑战并进列表就是这种行。
 * 把它算进 total 会按它多算出一页，翻过去是空的。
 */
export function createPagedList({
  els,
  skeletonCols,
  initialPageSize = 20,
  fetchPage,
  renderRows,
  onBeforeLoad = () => {},
  onLoaded = () => {},
  onError = (error) => error.message || "列表加载失败，请检查网络或登录状态。",
  afterRender = () => {},
}) {
  const { rows, emptyTip, errorTip, errorText, totalTip, prevBtn, nextBtn, retryBtn, pageSizeSelect, checkAll } = els;
  let items = [];
  let page = 1;
  let pageSize = initialPageSize;
  let totalCount = 0;
  let extraCount = 0; // 钉在首页的附加行，只进「共 N 条」，不进页数
  let state = "idle"; // idle | loading | error
  let hasLoaded = false;
  let loadToken = 0; // 并发防抖：只渲染最后一次请求的结果

  const pageCount = () => Math.max(1, Math.ceil(totalCount / pageSize));

  function render() {
    page = Math.min(page, pageCount());
    if (checkAll) checkAll.checked = false;
    if (state === "loading" && hasLoaded) {
      // 已有列表时保留当前行，避免切换分区时骨架屏叠加、跳动。
      emptyTip.hidden = true;
      errorTip.hidden = true;
      totalTip.textContent = "正在加载…";
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      return;
    }
    if (state !== "idle") {
      rows.innerHTML = state === "loading" ? skeletonRows(skeletonCols) : "";
      emptyTip.hidden = true;
      errorTip.hidden = state !== "error";
      totalTip.textContent = state === "loading" ? "加载中…" : "共 0 条";
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      afterRender(state);
      return;
    }
    errorTip.hidden = true;
    renderRows(items);
    emptyTip.hidden = items.length > 0;
    totalTip.textContent = `共 ${totalCount + extraCount} 条 · 第 ${page}/${pageCount()} 页`;
    prevBtn.disabled = page <= 1;
    nextBtn.disabled = page >= pageCount();
    afterRender(state);
  }

  async function reload() {
    const token = ++loadToken;
    state = "loading";
    onBeforeLoad();
    render();
    try {
      const data = await fetchPage({ page, size: pageSize });
      if (token !== loadToken) return; // 已有更新的一次请求在途
      items = data.items || [];
      totalCount = data.total || 0;
      extraCount = data.extra_total || 0;
      hasLoaded = true;
      onLoaded(data);
      state = "idle";
    } catch (error) {
      if (token !== loadToken) return;
      items = [];
      totalCount = 0;
      extraCount = 0;
      state = "error";
      if (errorText) errorText.textContent = onError(error);
    }
    render();
  }

  prevBtn.addEventListener("click", () => {
    if (page > 1) {
      page -= 1;
      reload();
    }
  });
  nextBtn.addEventListener("click", () => {
    if (page < pageCount()) {
      page += 1;
      reload();
    }
  });
  retryBtn?.addEventListener("click", reload);
  pageSizeSelect?.addEventListener("change", (event) => {
    pageSize = Number(event.target.value) || initialPageSize;
    page = 1;
    reload();
  });

  return {
    reload,
    get items() { return items; },
    get page() { return page; },
    set page(value) { page = Math.max(1, value); },
    get pageSize() { return pageSize; },
    get totalCount() { return totalCount; },
    get state() { return state; },
    // 删除当前页最后一条后调用：避免停在已不存在的一页。
    retreatIfEmpty() {
      if (items.length === 1 && page > 1) page -= 1;
    },
  };
}
