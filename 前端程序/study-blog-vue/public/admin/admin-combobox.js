// 所属试卷远程搜索组合框：考试链接页的新建 Modal 与筛选栏共用。
// 为什么不各自写一份：搜索防抖、乱序保护、键盘导航、模糊匹配提示全是
// 容易抄错细节的活，第二份拷贝就是下一个评审项（escapeHtml 的前科）。
//
// 数据量策略（单一来源，两处同行为）：
// - 每次请求 status 可选、pageSize 默认 20，绝不把全量卷塞前端；
// - 超出时下拉底部提示「共 N 条匹配，仅显示前 20 条——请继续输入关键词缩小范围」；
// - 必须点选结果才生效（onSelect 回调由消费方写 id），重新输入走 onInput 回调。

import { adminRequest } from "./admin-api.js";
import { escapeHtml } from "./admin-ui.js";

export const paperLabel = (paper) =>
  `${paper.paper_id_no || ""} ${paper.title || ""}`.trim() || `试卷 #${paper.id}`;

/**
 * @param {object} opts
 * @param {HTMLInputElement} opts.input  可见输入框（role=combobox）
 * @param {HTMLElement}      opts.list   结果面板（role=listbox）
 * @param {string}  [opts.status]        只搜某种状态的卷（Modal 传 "published"；筛选栏不传 = 全部）
 * @param {number}  [opts.pageSize]
 * @param {(paper: object) => void} opts.onSelect  点选结果（鼠标或 Enter）
 * @param {() => void} [opts.onInput]    用户重新输入（消费方在此清除已选 id）
 * @param {() => string} [opts.focusKeyword] 聚焦时的搜索词（默认取输入框当前文本）
 * @param {() => boolean} [opts.canOpen] 返回 false 时聚焦不展开（只读 / 编辑态）
 * @param {() => string} [opts.revertLabel] 失焦时把文本还原成当前选中的标签，
 *                                          避免「字面像选了、其实没选」的假状态
 */
export function createPaperPicker({ input, list, status = "", pageSize = 20, onSelect, onInput, focusKeyword, canOpen, revertLabel }) {
  let timer = 0;
  let seq = 0; // 乱序保护：慢的旧响应不得覆盖新结果

  const close = () => {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  };

  const render = (items, total) => {
    if (!items.length) {
      list.innerHTML = '<div class="paper-list-note">没有匹配的试卷，换个关键词试试。</div>';
    } else {
      list.innerHTML =
        items
          .map(
            (paper, index) => `
        <div class="paper-option" role="option" id="${input.id}Opt${index}" data-id="${paper.id}" aria-selected="false">
          <span class="no">${escapeHtml(paper.paper_id_no || `#${paper.id}`)}</span>
          <span>${escapeHtml(paper.title || "")}</span>
        </div>`,
          )
          .join("") +
        (total > items.length
          ? `<div class="paper-list-note">共 ${total} 条匹配，仅显示前 ${items.length} 条——请继续输入关键词缩小范围。</div>`
          : "");
      for (const opt of list.querySelectorAll(".paper-option")) {
        opt.addEventListener("click", () => {
          const paper = items.find((item) => String(item.id) === opt.dataset.id);
          if (paper) {
            onSelect(paper);
            close();
          }
        });
      }
    }
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  };

  const search = async (keyword) => {
    const ticket = ++seq;
    const params = new URLSearchParams({ page: "1", size: String(pageSize) });
    if (status) params.set("status", status);
    if (keyword) params.set("keyword", keyword);
    try {
      const data = await adminRequest(`/papers?${params}`);
      if (ticket !== seq) return; // 已有更新的请求在飞，这份结果作废
      render(data.items || [], data.total ?? (data.items || []).length);
    } catch {
      if (ticket !== seq) return;
      list.innerHTML = '<div class="paper-list-note">搜索失败，请重试。</div>';
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }
  };

  // 聚焦即拉最近一页（不防抖）：纯下拉选择的场景零输入可用。
  input.addEventListener("focus", () => {
    if (canOpen && !canOpen()) return;
    search(focusKeyword ? focusKeyword() : input.value.trim());
  });
  input.addEventListener("input", () => {
    onInput?.();
    clearTimeout(timer);
    timer = setTimeout(() => search(input.value.trim()), 300);
  });
  input.addEventListener("keydown", (event) => {
    const options = [...list.querySelectorAll(".paper-option")];
    if (event.key === "Escape") {
      close();
      return;
    }
    if (list.hidden || !options.length) {
      if (event.key === "ArrowDown") search(focusKeyword ? focusKeyword() : input.value.trim());
      return;
    }
    const current = options.findIndex((opt) => opt.classList.contains("active"));
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const next =
        event.key === "ArrowDown" ? (current + 1) % options.length : (current - 1 + options.length) % options.length;
      options.forEach((opt, index) => {
        opt.classList.toggle("active", index === next);
        opt.setAttribute("aria-selected", String(index === next));
      });
      input.setAttribute("aria-activedescendant", options[next].id);
    } else if (event.key === "Enter" && current >= 0) {
      event.preventDefault();
      options[current].click();
    }
  });
  input.addEventListener("blur", () => {
    close();
    // 没点选就失焦：还原成当前选中项的标签，杜绝「字面像选了、其实没选」。
    if (revertLabel) input.value = revertLabel();
  });
  // 抢在 blur 之前：选项的 click 要先于输入框失焦关闭列表发生。
  list.addEventListener("mousedown", (event) => event.preventDefault());

  return { close, search };
}
