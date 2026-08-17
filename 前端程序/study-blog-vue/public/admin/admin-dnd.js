// 后台通用拖拽排序器。从 papers.js:888-934 的实现抽出并参数化。
//
// papers.js 那版绑死了 #selectedRows 这一个节点 + 全局 selected 数组，按 dataset.index
// 操作，单层平铺——章节/课时是两层嵌套且课时要跨章节移动，直接复用不可能。这里改成：
//   · 顺序从 DOM 的 data-id 序列读，不依赖调用方的状态数组；
//   · 同 group 的容器之间可以互相 drop（跨容器移动带 fromParentId / toParentId）；
//   · 先移动 DOM（乐观更新）再回调，请求失败由调用方 revert()。
//
// papers.js 本次不改——它工作正常，动一个已发布功能只为了统一实现，不划算。
// 等 nodes.html 稳定后再单独做一次迁移。

// 模块级单例：同一时刻全页只可能有一次拖拽，没必要每实例存一份。
let dragging = null; // { el, id, from, homeParent, homeNext, idsBefore }
let busy = false; // 有排序请求在途：拒绝新的 dragstart，避免并发把顺序打乱
const groups = new Map(); // groupName -> Set<instance>

// 松开鼠标时清掉所有被临时置为可拖的项：按住手柄却没拖（或拖拽被取消）时，
// 不能残留 draggable=true——否则下次不用手柄也能拖动。
document.addEventListener("mouseup", () => {
  for (const el of document.querySelectorAll("[data-dnd] [draggable='true']")) {
    el.draggable = false;
  }
});

const isDisabled = (opts) =>
  typeof opts.disabled === "function" ? Boolean(opts.disabled()) : Boolean(opts.disabled);

/**
 * 为一个容器安装拖拽排序。每个可排序容器实例化一次。
 *
 * @param {HTMLElement} containerEl 直接包裹可排序项的元素（<ol>/<ul>/<tbody>）
 * @param {object}      opts
 * @param {string}      [opts.items=".dnd-item"] 可排序项选择器（也可用 "[data-id]"）
 * @param {string}      [opts.grip=".drag-grip"] 手柄选择器：只有从手柄按下才放行拖拽
 * @param {string}      [opts.group]      分组名；同名分组的容器之间可互相 drop
 * @param {*}           [opts.parentId]   本容器的业务父级 id，原样回传给 onReorder
 * @param {boolean|function} [opts.disabled] 只读态
 * @param {function}    opts.onReorder    见下方 detail 说明，可返回 Promise
 * @returns {{destroy: function, refresh: function, disabled: boolean}}
 */
export function createSortable(containerEl, opts = {}) {
  const cfg = {
    items: ".dnd-item",
    grip: ".drag-grip",
    group: null,
    parentId: null,
    disabled: false,
    onReorder: async () => {},
    ...opts,
  };

  containerEl.setAttribute("data-dnd", "");
  const instance = { el: containerEl, cfg };
  if (cfg.group) {
    if (!groups.has(cfg.group)) groups.set(cfg.group, new Set());
    groups.get(cfg.group).add(instance);
  }

  const itemsOf = (el) => [...el.querySelectorAll(cfg.items)];
  const idsOf = (el) => itemsOf(el).map((node) => node.dataset.id);
  // 落点容器可能是别的实例：跨容器时要用**那个**实例的选择器读顺序。
  const idsOfContainer = (el) => {
    const owner = ownerOf(el) || instance;
    return [...el.querySelectorAll(owner.cfg.items)].map((node) => node.dataset.id);
  };

  function ownerOf(el) {
    if (!cfg.group) return el === containerEl ? instance : null;
    for (const other of groups.get(cfg.group) || []) if (other.el === el) return other;
    return null;
  }

  // refresh(): 重渲染后重新打 .dnd-item 类（视觉规则挂在这个类上，不绑具体 id）
  function refresh() {
    for (const node of itemsOf(containerEl)) node.classList.add("dnd-item");
  }
  refresh();

  function clearMarks() {
    for (const el of document.querySelectorAll("[data-dnd]")) {
      el.classList.remove("dnd-over");
      for (const node of el.children) node.classList.remove("drop-before", "drop-after");
    }
  }

  function onMouseDown(event) {
    if (isDisabled(cfg)) return;
    const grip = event.target.closest(cfg.grip);
    if (!grip || grip.classList.contains("disabled")) return;
    const item = grip.closest(cfg.items);
    if (item && containerEl.contains(item)) item.draggable = true;
  }

  function onDragStart(event) {
    const item = event.target.closest(cfg.items);
    if (!item || !containerEl.contains(item)) return;
    if (busy || isDisabled(cfg)) {
      event.preventDefault();
      return;
    }
    dragging = {
      el: item,
      id: item.dataset.id,
      from: instance,
      // revert 用：记住原来的父节点与后继兄弟，还原就是插回这两者之间
      homeParent: item.parentElement,
      homeNext: item.nextElementSibling,
      // drop 后对比顺序：未变化时（如拖回自身附近）不发保存请求
      idsBefore: idsOfContainer(containerEl),
    };
    item.classList.add("dragging");
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      // Firefox 不 setData 就不触发 drag
      try {
        event.dataTransfer.setData("text/plain", item.dataset.id || "");
      } catch {
        /* 某些浏览器在 dragstart 外读写会抛，忽略即可 */
      }
    }
  }

  const sameGroup = () =>
    dragging && (dragging.from === instance || (cfg.group && dragging.from.cfg.group === cfg.group));

  // 落点：指针在目标项中线以上 → 插到它前面，以下 → 后面；不在任何项上 → 追加末尾；
  // 目标就是被拖项本身 → 标记 self，由 onDrop 判定为 no-op（不能走到 appendChild）。
  function dropTarget(event) {
    const item = event.target.closest(cfg.items);
    if (!item || !containerEl.contains(item)) return { item: null, before: false, self: false };
    if (item === dragging.el) return { item: null, before: false, self: true };
    const rect = item.getBoundingClientRect();
    return { item, before: (event.clientY || 0) < rect.top + rect.height / 2, self: false };
  }

  function onDragOver(event) {
    if (!sameGroup()) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    containerEl.classList.add("dnd-over");
    const { item, before } = dropTarget(event);
    for (const node of itemsOf(containerEl)) node.classList.remove("drop-before", "drop-after");
    if (item) item.classList.toggle(before ? "drop-before" : "drop-after", true);
  }

  function onDragLeave(event) {
    // 只有真正离开容器才清高亮：子元素之间移动也会冒泡 dragleave
    if (event.relatedTarget && containerEl.contains(event.relatedTarget)) return;
    containerEl.classList.remove("dnd-over");
  }

  async function onDrop(event) {
    if (!sameGroup()) return;
    event.preventDefault();
    const moved = dragging;
    const fromInstance = moved.from;
    const target = dropTarget(event);

    // 拖到自身：顺序没动，不发请求（原实现会走到 appendChild 把项甩到末尾）。
    if (target.self) {
      cleanup();
      return;
    }

    // 乐观更新：先把节点挪到位，界面立刻是对的
    if (target.item) containerEl.insertBefore(moved.el, target.before ? target.item : target.item.nextElementSibling);
    else containerEl.appendChild(moved.el);

    const crossContainer = fromInstance !== instance;
    // 顺序未变化（例如拖回原位或相邻位置）→ 不发保存请求
    const changed =
      crossContainer || idsOfContainer(containerEl).join(",") !== moved.idsBefore.join(",");
    if (!changed) {
      cleanup();
      return;
    }

    const detail = {
      movedId: moved.id,
      toParentId: cfg.parentId,
      fromParentId: fromInstance.cfg.parentId,
      crossContainer,
      orderedIds: idsOfContainer(containerEl),
      sourceOrderedIds: crossContainer ? idsOfContainer(fromInstance.el) : null,
      revert: () => moved.homeParent.insertBefore(moved.el, moved.homeNext),
    };

    cleanup();
    busy = true;
    try {
      await cfg.onReorder(detail);
    } finally {
      busy = false;
    }
  }

  function cleanup() {
    if (dragging) {
      dragging.el.classList.remove("dragging");
      dragging.el.draggable = false;
    }
    dragging = null;
    clearMarks();
  }

  containerEl.addEventListener("mousedown", onMouseDown);
  containerEl.addEventListener("dragstart", onDragStart);
  containerEl.addEventListener("dragover", onDragOver);
  containerEl.addEventListener("dragleave", onDragLeave);
  containerEl.addEventListener("drop", onDrop);
  containerEl.addEventListener("dragend", cleanup);

  return {
    refresh,
    destroy() {
      containerEl.removeEventListener("mousedown", onMouseDown);
      containerEl.removeEventListener("dragstart", onDragStart);
      containerEl.removeEventListener("dragover", onDragOver);
      containerEl.removeEventListener("dragleave", onDragLeave);
      containerEl.removeEventListener("drop", onDrop);
      containerEl.removeEventListener("dragend", cleanup);
      containerEl.removeAttribute("data-dnd");
      groups.get(cfg.group)?.delete(instance);
    },
    get disabled() {
      return isDisabled(cfg);
    },
    set disabled(value) {
      cfg.disabled = value;
    },
    get ids() {
      return idsOf(containerEl);
    },
  };
}

/** 页面重建 DOM 前调用：销毁一批实例，避免旧容器留在 group 里造成跨容器误判。 */
export function destroyAll(instances) {
  for (const item of instances) item?.destroy?.();
  instances.length = 0;
}
