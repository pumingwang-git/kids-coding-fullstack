// 轻量音效：Web Audio 合成，零资源文件。
// 正确=上扬音 / 错误=低沉音 / 胜利=琶音 / 星星=叮
let ctx = null;

function getCtx() {
  if (!ctx) {
    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
    } catch {
      ctx = null;
    }
  }
  if (ctx && ctx.state === 'suspended') ctx.resume();
  return ctx;
}

export function playTone(freq, dur = 0.15, type = 'sine', gain = 0.2, delay = 0) {
  const c = getCtx();
  if (!c) return;
  try {
    const startAt = c.currentTime + delay;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.value = freq;
    g.gain.setValueAtTime(gain, startAt);
    g.gain.exponentialRampToValueAtTime(0.001, startAt + dur);
    o.connect(g);
    g.connect(c.destination);
    o.start(startAt);
    o.stop(startAt + dur + 0.02);
  } catch {
    /* ignore */
  }
}

export function playCorrect() {
  playTone(660, 0.12);
  playTone(880, 0.15, 'sine', 0.2, 0.09);
}

export function playWrong() {
  playTone(180, 0.18, 'square', 0.07);
}

export function playWin() {
  [523, 659, 784, 1047].forEach((f, i) => playTone(f, 0.18, 'sine', 0.22, i * 0.11));
}

export function playStar() {
  playTone(1318, 0.1, 'triangle', 0.18);
}
