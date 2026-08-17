// CDP 实测脚本：打开字母乐园，检查 speechSynthesis 与自动跳转
import { spawn } from 'node:child_process';

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const URL = process.argv[2] || 'http://127.0.0.1:8603/?age=3-6&mode=letter';

const chrome = spawn(CHROME, [
  '--headless=new',
  '--disable-gpu',
  '--no-first-run',
  '--remote-debugging-port=9222',
  '--user-data-dir=C:/Users/asus/.workbuddy/binaries/node/workspace/.chrome-test-profile',
  '--autoplay-policy=no-user-gesture-required',
  '--mute-audio=false',
  URL
], { stdio: 'ignore' });

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function getJson(url) {
  const res = await fetch(url);
  return res.json();
}

async function connectWs(url) {
  const ws = new WebSocket(url);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });
  return ws;
}

let msgId = 0;
const pending = new Map();
function send(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function main() {
  await sleep(2500);
  // 获取页面列表
  let targets;
  try {
    targets = await getJson('http://127.0.0.1:9222/json');
  } catch (e) {
    console.log('CDP 连接失败:', e.message);
    chrome.kill();
    return;
  }
  const page = targets.find((t) => t.type === 'page');
  if (!page) {
    console.log('未找到页面 target');
    chrome.kill();
    return;
  }
  const ws = await connectWs(page.webSocketDebuggerUrl);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else resolve(msg.result);
    }
  };

  async function evalJs(expression, awaitPromise = false) {
    const r = await send(ws, 'Runtime.evaluate', {
      expression,
      awaitPromise,
      returnByValue: true
    });
    if (r.exceptionDetails) {
      return { __error: r.exceptionDetails.exception?.description || JSON.stringify(r.exceptionDetails) };
    }
    return r.result?.value;
  }

  // 1. speechSynthesis 检查
  const speechCheck = await evalJs(`(() => {
    const out = { hasSpeech: 'speechSynthesis' in window };
    if (out.hasSpeech) {
      const voices = window.speechSynthesis.getVoices();
      out.voiceCount = voices.length;
      out.voices = voices.map(v => v.lang + ' / ' + v.name).slice(0, 20);
      out.speaking = window.speechSynthesis.speaking;
      out.pending = window.speechSynthesis.pending;
    }
    return out;
  })()`);
  console.log('=== speechSynthesis ===');
  console.log(JSON.stringify(speechCheck, null, 2));

  // 2. 尝试 speak 一个字母，看状态变化
  const speakTest = await evalJs(`(async () => {
    if (!('speechSynthesis' in window)) return { skipped: true };
    const u = new SpeechSynthesisUtterance('a');
    u.lang = 'en-US';
    let started = false, errored = null;
    u.onstart = () => { started = true; };
    u.onerror = (e) => { errored = e.error; };
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
    await new Promise(r => setTimeout(r, 1500));
    return { started, errored, speaking: window.speechSynthesis.speaking, pending: window.speechSynthesis.pending };
  })()`, true);
  console.log('=== speak 测试 ===');
  console.log(JSON.stringify(speakTest, null, 2));

  // 3. 页面当前字母
  const cur = await evalJs(`(() => {
    const el = document.querySelector('.center-letter');
    return el ? el.textContent : '(未找到 .center-letter)';
  })()`);
  console.log('=== 当前字母 ===', JSON.stringify(cur));

  // 4. 模拟按键，检查自动跳转：连续打正确字母
  async function press(key) {
    await evalJs(`(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: '${key}', bubbles: true }));
    })()`);
  }
  const firstLetter = typeof cur === 'string' && /^[a-z]$/.test(cur) ? cur : 'a';
  await press(firstLetter);
  await sleep(700); // 等 520ms 发光 + 跳转
  const after1 = await evalJs(`(() => {
    const el = document.querySelector('.center-letter');
    return el ? el.textContent : '(finished)';
  })()`);
  console.log('=== 打第一个字母后 ===', JSON.stringify(after1));

  // 再打一个
  if (typeof after1 === 'string' && /^[a-z]$/.test(after1)) {
    await press(after1);
    await sleep(700);
    const after2 = await evalJs(`(() => {
      const el = document.querySelector('.center-letter');
      return el ? el.textContent : '(finished)';
    })()`);
    console.log('=== 打第二个字母后 ===', JSON.stringify(after2));
  }

  // 5. 检查是否有 JS 错误
  const errs = await evalJs(`(() => {
    // 读取页面内收集的错误（通过 window.__errors 不可用，改用监听）— 简化为空
    return 'ok';
  })()`);

  ws.close();
  chrome.kill();
}

main().catch((e) => {
  console.log('测试失败:', e.message);
  chrome.kill();
});
