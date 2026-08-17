// 滑块验证码交互组件：加载挑战 → 拖拽拼图块 → 松手立即调服务端校验。
// 通过：显示「✓ 验证通过」并锁定。
// 未对齐：拼图块复位，提示重试（同一张图，最多 5 次），不换图。
// 已失效（5 次用完/过期）：自动换一张新挑战。
// 坐标换算：轨道可能被 CSS 缩放（窄窗口），内部一律用图片像素（320x160），
// 显示时按 实际宽度/320 换算，保证拖拽距离与提交坐标一致。

const TRACK_W = 320;
const TRACK_H = 160;

export function createSliderCaptcha(container, fetchChallenge, verifyChallenge) {
  let challenge = null;
  let pieceLeft = 0; // 图片像素坐标
  let verified = false;
  let busy = false;
  let loading = false;
  let pieceEl = null;
  let hintEl = null;
  let trackEl = null;
  let dragging = false;
  let startImageX = 0;
  let startLeft = 0;

  function toImageX(clientX) {
    const rect = trackEl.getBoundingClientRect();
    return ((clientX - rect.left) * TRACK_W) / rect.width;
  }

  function toImageY(clientY) {
    const rect = trackEl.getBoundingClientRect();
    return ((clientY - rect.top) * TRACK_H) / rect.height;
  }

  function applyPiecePosition() {
    const rect = trackEl.getBoundingClientRect();
    pieceEl.style.left = `${(pieceLeft * rect.width) / TRACK_W}px`;
  }

  function render() {
    container.innerHTML = `
      <div class="slider-track">
        <img class="slider-bg-img" src="${challenge.background}" draggable="false" alt="滑块验证码背景">
        <img class="slider-piece" src="${challenge.piece}" draggable="false" alt="拼图块" style="left:0px">
        <button type="button" class="slider-refresh" title="换一张">↻</button>
      </div>
      <p class="slider-hint">按住拼图块，拖动到缺口位置</p>`;
    pieceEl = container.querySelector(".slider-piece");
    hintEl = container.querySelector(".slider-hint");
    trackEl = container.querySelector(".slider-track");
    trackEl.addEventListener("pointerdown", onDown);
    const refreshButton = container.querySelector(".slider-refresh");
    // 刷新按钮位于轨道内部。阻止 pointerdown 冒泡，避免它被误认为是一次拖拽起点。
    refreshButton.addEventListener("pointerdown", (event) => event.stopPropagation());
    refreshButton.addEventListener("click", (event) => {
      event.preventDefault();
      refresh();
    });
  }

  function onDown(event) {
    if (busy || verified) return;
    event.preventDefault();
    const px = toImageX(event.clientX);
    const py = toImageY(event.clientY);
    const size = challenge.piece_size;
    // 只有按在拼图块本身（含当前已拖动位置）才开始拖拽
    if (py < challenge.piece_y || py > challenge.piece_y + size) return;
    if (px < pieceLeft || px > pieceLeft + size) return;
    dragging = true;
    startImageX = toImageX(event.clientX); // 统一用图片像素，避免单位混用
    startLeft = pieceLeft;
    pieceEl.classList.add("dragging");
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function onMove(event) {
    if (!dragging) return;
    const next = Math.min(
      Math.max(startLeft + (toImageX(event.clientX) - startImageX), 0),
      TRACK_W - challenge.piece_size
    );
    pieceLeft = next;
    applyPiecePosition();
  }

  function onUp() {
    if (!dragging) return;
    dragging = false;
    pieceEl.classList.remove("dragging");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    pieceLeft = Math.round(pieceLeft);
    if (pieceLeft <= 0) {
      hintEl.textContent = "请拖动拼图块到缺口位置";
      return;
    }
    verify();
  }

  async function verify() {
    // 锁定本次请求对应的挑战；任何旧请求都不能改写后来刷新的挑战状态。
    const verifyingChallenge = challenge;
    const verifyingX = pieceLeft;
    busy = true;
    try {
      await verifyChallenge({ slider_id: verifyingChallenge.challenge_id, slider_x: verifyingX });
      if (challenge !== verifyingChallenge) return;
      verified = true;
      trackEl.classList.add("verified");
      pieceEl.classList.add("verified");
      hintEl.textContent = "✓ 验证通过";
      hintEl.classList.add("verified-hint");
    } catch (reason) {
      if (challenge !== verifyingChallenge) return;
      const message = reason.message || "";
      if (message.includes("失效")) {
        hintEl.textContent = "验证码已失效，正在刷新…";
        await refresh({ allowWhileBusy: true });
      } else {
        // 未对齐：复位拼图块，同一张图重试，不换图
        pieceLeft = 0;
        applyPiecePosition();
        hintEl.textContent = "未对齐，请再试一次";
      }
    } finally {
      busy = false;
    }
  }

  async function refresh({ allowWhileBusy = false } = {}) {
    // 验证成功后保持当前挑战；只允许用户随后主动点击刷新按钮换题。
    if (loading || (busy && !allowWhileBusy)) return;
    loading = true;
    try {
      challenge = await fetchChallenge();
      pieceLeft = 0;
      verified = false;
      render();
    } finally {
      loading = false;
    }
  }

  // 清除已验证状态（登录失败等场景），保留当前挑战
  function reset() {
    pieceLeft = 0;
    verified = false;
    if (pieceEl) {
      applyPiecePosition();
      trackEl.classList.remove("verified");
      pieceEl.classList.remove("verified");
      hintEl.classList.remove("verified-hint");
      hintEl.textContent = "按住拼图块，拖动到缺口位置";
    }
  }

  // 未完成验证时返回 null，登录表单据此拦截
  function value() {
    return challenge && verified
      ? { slider_id: challenge.challenge_id, slider_x: pieceLeft }
      : null;
  }

  return { refresh, reset, value };
}
