// 后台通用交互原语：轻提示与受控对话框。
// 统一替代 alert / confirm / prompt——原生弹窗会阻塞渲染线程、无法承载表单校验，
// 且在部分浏览器的后台标签页被静默忽略，B 端批量操作不能依赖它。

const TOAST_DURATION = { success: 2600, info: 2600, error: 4200 };

function toastLayer() {
  let layer = document.getElementById("toastLayer");
  if (!layer) {
    layer = document.createElement("div");
    layer.id = "toastLayer";
    layer.className = "toast-layer";
    // 屏幕阅读器需要在不抢焦点的前提下播报操作结果。
    layer.setAttribute("role", "status");
    layer.setAttribute("aria-live", "polite");
    document.body.appendChild(layer);
  }
  return layer;
}

export function toast(message, type = "success") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  toastLayer().appendChild(node);
  const remove = () => {
    node.classList.add("leaving");
    setTimeout(() => node.remove(), 200);
  };
  const timer = setTimeout(remove, TOAST_DURATION[type] || TOAST_DURATION.info);
  node.addEventListener("click", () => {
    clearTimeout(timer);
    remove();
  });
  return remove;
}

// Tab 循环：对话框打开期间焦点不得逃逸到背后的列表。
const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function trapFocus(container) {
  const onKeydown = (event) => {
    if (event.key !== "Tab") return;
    const items = [...container.querySelectorAll(FOCUSABLE)].filter(
      (item) => item.offsetParent !== null || item === document.activeElement,
    );
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
  container.addEventListener("keydown", onKeydown);
  return () => container.removeEventListener("keydown", onKeydown);
}

/**
 * 打开 / 关闭 .modal-mask 遮罩。
 *
 * ⚠️ 只把元素显示出来是不够的：admin.css 里 .modal-mask 默认 opacity:0 +
 * pointer-events:none，必须加 .show 才真正可见。漏掉这一句的表现是
 * 「按钮点了没反应」——Modal 其实开了，只是完全透明，排查起来很费时间。
 * 抽成公共函数就是为了不让每个新页面再踩一次。
 *
 * @returns 焦点循环的解绑函数，关闭时传回 closeMask。
 */
export function openMask(mask, { focusSelector } = {}) {
  // 可访问性：只调透明度的话，关掉的 Modal 仍留在可访问性树里，读屏会把
  // 背后的整份表单再念一遍。hidden + inert 双保险（inert 拦焦点与交互，
  // hidden 拦渲染与 a11y 树）；注意 admin.css 必须补 .modal-mask[hidden]，
  // 否则 author 的 display:flex 会压过 UA 的 [hidden] 规则。
  mask.hidden = false;
  mask.removeAttribute("inert");
  void mask.offsetWidth; // display:none → flex 的同帧类切换不触发过渡，强制重排保住入场动画
  mask.classList.add("show");
  document.body.style.overflow = "hidden";
  const box = mask.querySelector(".modal");
  const release = box ? trapFocus(box) : null;
  if (focusSelector) mask.querySelector(focusSelector)?.focus();
  return release;
}

export function closeMask(mask, release) {
  release?.();
  mask.classList.remove("show");
  // 立即摘出可访问性树：代价是放弃 0.2s 的关闭淡出，换来读屏不再念到已关闭的表单。
  mask.hidden = true;
  mask.setAttribute("inert", "");
  document.body.style.overflow = "";
}

export const isMaskOpen = (mask) => mask.classList.contains("show");

export function escapeHtml(value = "") {
  return String(value).replace(
    /[&<>"']/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
  );
}

// ==================== 时间格式化（papers.js / exam-links.js 两页共用，单源） ====================
// escapeHtml 曾经复制过两份、专门花一次评审合并——这三个函数别再开第二份。

export function fmtTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// datetime-local 是本地时区无时区串；提交前转成 ISO，服务端按 UTC 落库。
export const toIso = (local) => (local ? new Date(local).toISOString() : null);

export function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// ==================== 内联表单校验（从 questions.html 抽出，组卷页复用） ====================
// 字段级提示就地显示在输入框后；区块级提示（选项/填空答案/测试点）路由到
// 区块标题下方的 slot，可叠加多条。sectionSlots 形如：
// [{ selectors: '[name="correctOption"], .q-option', slotId: "optionsError" }]

export function clearFieldErrors(sectionSlotIds = [], root = document) {
  root.querySelectorAll(".field-error, .required-mark").forEach((node) => node.remove());
  root.querySelectorAll(".input-invalid, .invalid-field").forEach((node) => {
    node.classList.remove("input-invalid", "invalid-field");
    node.removeAttribute("aria-invalid");
  });
  sectionSlotIds.forEach((id) => {
    const slot = document.getElementById(id);
    if (slot) {
      slot.hidden = true;
      slot.replaceChildren();
    }
  });
}

export function showFieldErrors(errors, sectionSlots = [], root = document) {
  clearFieldErrors(sectionSlots.map((rule) => rule.slotId), root);
  errors.forEach(({ selector, message }) => {
    const target = root.querySelector(selector);
    if (!target) return;
    const slotRule = sectionSlots.find((rule) => target.matches(rule.selectors));
    const slotEl = slotRule && document.getElementById(slotRule.slotId);
    if (slotEl) {
      slotEl.hidden = false;
      const line = document.createElement("div");
      line.textContent = message;
      slotEl.appendChild(line);
      target.closest(".card")?.classList.add("invalid-field");
      return;
    }
    target.classList.add("input-invalid");
    target.setAttribute("aria-invalid", "true");
    const container =
      target.closest("label.field") ||
      target.closest(".row-select") ||
      target.closest(".card") ||
      target.parentElement;
    container?.classList.add("invalid-field");
    if (container && !container.querySelector(":scope > .required-mark")) {
      const star = document.createElement("span");
      star.className = "required-mark";
      star.textContent = "*";
      star.setAttribute("aria-label", "必填项");
      container.prepend(star);
    }
    const tip = document.createElement("small");
    tip.className = "field-error";
    tip.textContent = message;
    target.insertAdjacentElement("afterend", tip);
  });
  const first = root.querySelector(`${errors[0]?.selector || ""}`);
  if (first) {
    first.scrollIntoView({ behavior: "smooth", block: "center" });
    first.focus({ preventScroll: true });
  }
}

/**
 * 受控对话框。resolve 的值由 `resolveWith` 决定：
 * - 确认按钮：返回 `readValue()` 的结果，返回 undefined 表示校验未通过、保持打开。
 * - 取消 / ESC / 遮罩：返回 null。
 */
function openDialog({ title, bodyHtml, confirmText = "确定", cancelText = "取消", danger = false, onMount }) {
  return new Promise((resolve) => {
    const previousFocus = document.activeElement;
    const mask = document.createElement("div");
    mask.className = "dialog-mask";
    mask.innerHTML = `
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dialogTitle">
        <h3 id="dialogTitle">${escapeHtml(title)}</h3>
        <div class="dialog-body">${bodyHtml}</div>
        <div class="dialog-foot">
          <button class="btn" type="button" data-role="cancel">${escapeHtml(cancelText)}</button>
          <button class="btn primary${danger ? " danger-solid" : ""}" type="button" data-role="confirm">${escapeHtml(confirmText)}</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    const dialog = mask.querySelector(".dialog");
    const releaseFocus = trapFocus(dialog);

    const close = (value) => {
      releaseFocus();
      document.removeEventListener("keydown", onKeydown, true);
      mask.remove();
      previousFocus?.focus?.();
      resolve(value);
    };
    const onKeydown = (event) => {
      if (event.key !== "Escape") return;
      // 对话框叠在录入 Modal 之上，ESC 必须只关最上层。
      event.stopPropagation();
      close(null);
    };
    document.addEventListener("keydown", onKeydown, true);
    mask.addEventListener("mousedown", (event) => {
      if (event.target === mask) close(null);
    });
    mask.querySelector('[data-role="cancel"]').addEventListener("click", () => close(null));

    const readValue = onMount?.(dialog) || (() => true);
    mask.querySelector('[data-role="confirm"]').addEventListener("click", () => {
      const value = readValue();
      if (value !== undefined) close(value);
    });

    requestAnimationFrame(() => {
      mask.classList.add("show");
      (dialog.querySelector("textarea, input, select") || dialog.querySelector('[data-role="confirm"]'))?.focus();
    });
  });
}

export function confirmDialog({ title, message, detail = "", confirmText = "确定", danger = false }) {
  return openDialog({
    title,
    danger,
    confirmText,
    bodyHtml: `<p>${escapeHtml(message)}</p>${detail ? `<p class="muted dialog-detail">${escapeHtml(detail)}</p>` : ""}`,
  }).then((value) => value === true);
}

export function promptDialog({
  title,
  message = "",
  label,
  placeholder = "",
  maxLength = 500,
  confirmText = "提交",
  danger = false,
  selectOptions = null,
}) {
  const inputHtml = Array.isArray(selectOptions)
    ? `<select data-role="input" required>${selectOptions
        .map(
          (option) =>
            `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`,
        )
        .join("")}</select>`
    : `<textarea data-role="input" rows="3" maxlength="${maxLength}" placeholder="${escapeHtml(placeholder)}"></textarea>`;
  return openDialog({
    title,
    danger,
    confirmText,
    bodyHtml: `
      ${message ? `<p>${escapeHtml(message)}</p>` : ""}
      <label class="field full">${escapeHtml(label)}
        ${inputHtml}
        <small class="field-error" data-role="error" hidden></small>
      </label>`,
    onMount(dialog) {
      const input = dialog.querySelector('[data-role="input"]');
      const error = dialog.querySelector('[data-role="error"]');
      return () => {
        const value = input.value.trim();
        if (!value) {
          input.classList.add("input-invalid");
          error.hidden = false;
          error.textContent = `请填写${label}。`;
          input.focus();
          return undefined; // 校验未过：对话框保持打开
        }
        return value;
      };
    },
  });
}
