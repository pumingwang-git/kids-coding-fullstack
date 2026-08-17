// Web Speech API 封装：单词/字母朗读，零后端成本。
// 浏览器兼容性：Chrome/Edge/Safari 均支持 speechSynthesis。
let voiceReady = false;

function pickVoice(lang) {
  if (!('speechSynthesis' in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  // 优先选目标语言的第一个可用 voice（Chrome 支持语言前缀匹配）
  return voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(lang.toLowerCase())) || null;
}

export function speak(text, opts = {}) {
  if (!('speechSynthesis' in window)) return;
  const lang = opts.lang || 'en-US';
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  utterance.rate = opts.rate ?? 0.85;
  utterance.pitch = opts.pitch ?? 1.05;
  const voice = pickVoice(lang);
  if (voice) utterance.voice = voice;
  // 连续发音时先打断上一次，避免排队堆积
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
  voiceReady = true;
}

export function speakWord(word, opts = {}) {
  speak(word, { lang: 'en-US', rate: 0.8, ...opts });
}

export function speakLetter(letter) {
  speak(letter, { lang: 'en-US', rate: 0.7, pitch: 1.2 });
}

export function cancelSpeak() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  if (audioEl) audioEl.pause();
}

// 有道发音 API（复用 qwerty-learner 的做法）：真人录音，质量远高于 Web Speech 合成。
// type: 1 = 英音，2 = 美音。加载失败自动回退 Web Speech。
let audioEl = null;

export function speakWordYoudao(word, type = 2) {
  if (!word) return;
  try {
    if (!audioEl) audioEl = new Audio();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    audioEl.src = `https://dict.youdao.com/dictvoice?audio=${encodeURIComponent(word)}&type=${type}`;
    audioEl.play().catch(() => speak(word, { lang: 'en-US', rate: 0.8 }));
  } catch {
    speak(word, { lang: 'en-US', rate: 0.8 });
  }
}
