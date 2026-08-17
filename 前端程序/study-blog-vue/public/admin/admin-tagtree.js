// 知识点树选择器：触发区 chips + 浮层三级树（阶段/主题/叶子）+ 搜索过滤。
// 从 questions.html 抽出，组卷 Modal（papers.js）的选题面板复用。
// 行为约定（与原实现逐条对齐，改动前请先读这段）：
// - 每级都可勾选为标签（一二级勾选 = 直接打父级标签，不级联全选下级）；
// - 点一级/二级标题 = 展开/收起（展开状态记入 openIds，重绘后保持）；点三级行 = 选择；
// - 勾选只更新状态 + chips + 摘要，不重绘整棵树：保持展开状态与滚动位置；
// - ESC 只关浮层（capture 阶段拦截，不连带关 Modal）；浮层按实际高度定位，避免跳位。

import { escapeHtml } from "./admin-ui.js";

export function createKnowledgeTree({ els, onChange = () => {} }) {
  const { trigger, hint, pop, filter, tree, summary, scrollContext } = els;
  let treeData = []; // 初始本地树；后端标签到位后由 setTree 覆盖
  const openIds = new Set(); // 记住用户展开的节点 id，重绘后保持树的界面不变
  let selected = []; // 选中项 id（叶子或任意层级节点）

  // 递归遍历全部节点（阶段/主题/叶子）。
  const allNodes = () => {
    const out = [];
    (function walk(nodes) {
      nodes.forEach((n) => {
        out.push(n);
        if (n.children) walk(n.children);
      });
    })(treeData);
    return out;
  };
  const nameOf = (id) => allNodes().find((n) => String(n.id) === String(id))?.name || id;
  const idOf = (name) => allNodes().find((n) => n.name === name)?.id;

  // 既接受 id 也接受名称（后端返回名称数组），归一化为 id 并去重。
  function normalize(values = []) {
    return [
      ...new Set(
        (values || [])
          .map((value) => (allNodes().some((n) => String(n.id) === String(value)) ? value : idOf(value)))
          .filter(Boolean),
      ),
    ];
  }

  function commit(values) {
    selected = normalize(values);
    onChange([...selected]);
  }

  function renderChips() {
    trigger.querySelectorAll(".kt-chip").forEach((c) => c.remove());
    if (hint) hint.style.display = selected.length ? "none" : "";
    selected.forEach((id) => {
      const chip = document.createElement("span");
      chip.className = "kt-chip";
      chip.innerHTML = `${escapeHtml(nameOf(id))}<button type="button" data-id="${escapeHtml(id)}" aria-label="移除">×</button>`;
      chip.querySelector("button").addEventListener("click", (e) => {
        e.stopPropagation();
        commit(selected.filter((item) => item !== id));
        renderChips();
        renderSummary();
        // 同步树中对应复选框，不重绘整棵树（保持展开状态）
        if (!pop.hidden) {
          const cb = tree.querySelector(
            `.node-check[data-id="${CSS.escape(id)}"], .leaf-check[data-id="${CSS.escape(id)}"]`,
          );
          if (cb) cb.checked = false;
        }
      });
      trigger.appendChild(chip);
    });
  }

  function renderSummary() {
    if (!summary) return;
    const names = selected.map(nameOf);
    summary.innerHTML = `已选 <b>${names.length}</b> 项${names.length ? `：${escapeHtml(names.join("、"))}` : ""}`;
  }

  function renderTree(filterText = "") {
    tree.innerHTML = "";
    const nodeVisible = (n, f) => n.name.includes(f) || (n.children || []).some((c) => nodeVisible(c, f));
    let visible = 0;
    // 递归渲染：一级=阶段、二级=主题、三级=叶子；每级都有复选框可勾选为标签。
    // 悬浮显示 desc（去括号后保留的说明）。
    const renderList = (nodes, depth) => {
      const ul = document.createElement("ul");
      if (depth === 0) ul.style.display = "block";
      nodes.forEach((node) => {
        if (filterText && !nodeVisible(node, filterText)) return;
        const isGroup = node.children && node.children.length;
        if (!isGroup) visible += 1;
        const li = document.createElement("li");
        li.className =
          (depth === 0 ? "kt-stage" : isGroup ? "kt-group" : "leaf") +
          (openIds.has(node.id) || (filterText && nodeVisible(node, filterText)) ? " open" : "");
        const nameTip = node.desc ? `title="${escapeHtml(node.desc)}"` : "";
        li.innerHTML =
          depth === 0
            ? `<div class="stage-head"><span class="arrow">▶</span>
              <input type="checkbox" class="node-check" data-id="${escapeHtml(node.id)}" />
              ${node.badge ? `<span class="kt-badge">${escapeHtml(node.badge)}</span>` : ""}
              <span class="kt-name" ${nameTip}>${escapeHtml(node.name)}</span></div>`
            : isGroup
              ? `<div class="group-head"><span class="arrow">▶</span>
              <input type="checkbox" class="node-check" data-id="${escapeHtml(node.id)}" />
              <span class="kt-name" ${nameTip}>${escapeHtml(node.name)}</span>
              ${node.hint ? `<span class="kt-hint">${escapeHtml(node.hint)}</span>` : ""}</div>`
              : `<input type="checkbox" class="leaf-check" data-id="${escapeHtml(node.id)}" />
              ${node.num ? `<span class="kt-num">${escapeHtml(node.num)}</span>` : ""}
              <span class="kt-name" ${nameTip}>${escapeHtml(node.name)}</span>`;
        const cb = li.querySelector(".node-check, .leaf-check");
        cb.checked = selected.includes(node.id);
        // 勾选只更新状态 + chips + 摘要，不重绘整棵树：保持展开状态与滚动位置。
        cb.addEventListener("change", () => {
          commit(cb.checked ? [...selected, node.id] : selected.filter((x) => x !== node.id));
          renderChips();
          renderSummary();
        });
        const head = li.querySelector(".stage-head, .group-head");
        if (head) {
          const toggleOpen = () => {
            li.classList.toggle("open");
            if (li.classList.contains("open")) openIds.add(node.id);
            else openIds.delete(node.id);
          };
          head.querySelector(".arrow").addEventListener("click", (e) => {
            e.stopPropagation();
            toggleOpen();
          });
          // 一级/二级：点标题 = 展开/收起（选择走复选框）
          head.addEventListener("click", (e) => {
            if (e.target.tagName === "INPUT") return;
            toggleOpen();
          });
        } else {
          // 三级：点行 = 选择知识点
          li.addEventListener("click", (e) => {
            if (e.target === cb) return;
            cb.click();
          });
        }
        if (isGroup) {
          const childUl = renderList(node.children, depth + 1);
          childUl.className = "children";
          li.appendChild(childUl);
        }
        ul.appendChild(li);
      });
      return ul;
    };
    tree.appendChild(renderList(treeData, 0));
    if (filterText && visible === 0)
      tree.innerHTML = '<li class="muted" style="padding:10px;font-size:12px">无匹配知识点</li>';
    renderSummary();
  }

  // 悬浮框：内容渲染完成后用实际高度定位，避免靠近视窗边缘时跳位。
  function position() {
    if (pop.hidden) return;
    const rect = trigger.getBoundingClientRect();
    const margin = 8;
    const popWidth = pop.offsetWidth || 300;
    const popHeight = pop.offsetHeight || 320;
    const left = Math.max(margin, Math.min(rect.left, window.innerWidth - popWidth - margin));
    const below = rect.bottom + 4;
    const top =
      below + popHeight <= window.innerHeight - margin
        ? below
        : Math.max(margin, rect.top - popHeight - 4);
    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;
  }

  function open() {
    pop.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    filter.value = "";
    renderTree();
    position();
    filter.focus();
  }

  function close() {
    pop.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
  }

  trigger.addEventListener("click", (e) => {
    if (e.target.closest(".kt-chip")) return; // 点 chips 的 × 由 chips 处理
    if (pop.hidden) open();
    else close();
  });
  trigger.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    trigger.click();
  });
  filter.addEventListener("input", (e) => {
    renderTree(e.target.value.trim());
    position();
  });
  document.addEventListener("mousedown", (e) => {
    if (pop.hidden) return;
    if (!pop.contains(e.target) && !trigger.contains(e.target)) close();
  });
  // ESC 只关悬浮框（capture 阶段拦截，避免连带关掉 Modal）。
  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key === "Escape" && !pop.hidden) {
        e.stopPropagation();
        close();
      }
    },
    true,
  );
  // 只在定位参照物移动时重新定位；不能捕获树自身的滚动事件。
  window.addEventListener("scroll", position);
  window.addEventListener("resize", position);
  scrollContext?.addEventListener("scroll", position);

  return {
    setTree(data) {
      treeData = data || [];
      selected = normalize(selected); // 树换数据源后重新归一化选中项
    },
    setSelected(values) {
      commit(values);
      renderChips();
      renderSummary();
    },
    getSelected: () => [...selected],
    normalize,
    nameOf,
    idOf,
    allNodes,
    getTreeData: () => treeData,
    refresh() {
      renderChips();
      renderSummary();
    },
    open,
    close,
  };
}
