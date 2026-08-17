// CDP 实测脚本 v2：有头 Chrome，不带 autoplay 豁免，模拟真实用户
// 检查：1) onMounted 自动 speak 是否被静音  2) 真实按键手势后 speak 是否恢复  3) 自动跳转
import { spawn } from 'node:child_process';

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const URL = process.argv[2] || 'http://127.0.0.1:8603/?age=3-6&mode=letter';
const WITH_AUTOPLAY_FLAG = process.argv[3] === 'autoplay-ok';

const args = [
  '--headless=new',
  '--disable-gpu',
  '--no-first-run',
  '--remote-debugging-port=9223',
  '--user-data-dir=C:/Users/asus/.workbuddy/binaries/node/workspace/.chrome-test-profile2'
];
if (WITH_AUTOPLAY_FLAG) args.push('--autoplay-policy=no-user-gesture-required');
args.push(URL);

const chrome = spawn(CHROME, args, { stdio: 'ignore' });

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
async function getJson(url) {
  const res = await fetch(url);
  return res.json();
}
async function connectWs(url) {
  const ws = new WebSocket(url);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
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
  await sleep(3000);
  let targets;
  try {
    targets = await getJson('http://127.0.0.1:9223/json');
  } catch (e) {
    console.log('CDP 连接失败:', e.message);
    chrome.kill();
    return;
  }
  const page = targets.find((t) => t.type === 'page');
  if (!page) { console.log('未找到页面 target'); chrome.kill(); return; }
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
    const r = await send(ws, 'Runtime.evaluate', { expression, awaitPromise, returnByValue: true });
    if (r.exceptionDetails) return { __error: r.exceptionDetails.exception?.description || JSON.stringify(r.exceptionDetails) };
    return r.result?.value;
  }

  // 页面刚加载完成：先挂一个全局语音事件监听器，记录自动 speak 的情况
  await evalJs(`(() => {
    window.__speechLog = [];
    if ('speechSynthesis' in window) {
      window.__speechLog.push('hasSpeech=true voices=' + window.speechSynthesis.getVoices().length);
      window.speechSynthesis.onvoiceschanged = () => {
        window.__speechLog.push('voiceschanged voices=' + window.speechSynthesis.getVoices().length);
      };
    }
    // 检查当前是否已在朗读（onMounted 已触发过自动 speak）
    window.__speechLog.push('speaking=' + (window.speechSynthesis?.speaking) + ' pending=' + (window.speechSynthesis?.pending));
    return 'hooked';
  })()`);

  await sleep(800);
  const log1 = await evalJs(`window.__speechLog`);
  console.log('=== 加载后语音状态 ===');
  console.log(JSON.stringify(log1, null, 2));

  // 手动 speak 测试（此时无用户手势）
  const noGestureSpeak = await evalJs(`(async () => {
    if (!('speechSynthesis' in window)) return { skipped: true };
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance('b');
    u.lang = 'en-US';
    let started = false, errored = null;
    u.onstart = () => { started = true; };
    u.onerror = (e) => { errored = e.error; };
    window.speechSynthesis.speak(u);
    await new Promise(r => setTimeout(r, 1200));
    return { started, errored, speaking: window.speechSynthesis.speaking };
  })()`, true);
  console.log('=== 无手势手动 speak ===');
  console.log(JSON.stringify(noGestureSpeak, null, 2));

  // 当前字母
  const cur = await evalJs(`document.querySelector('.center-letter')?.textContent || '(无)'`);
  console.log('=== 当前字母 ===', JSON.stringify(cur));

  // 用 Input.dispatchKeyEvent 发真实按键（isTrusted=true，构成用户手势）
  async function realKey(key) {
    await send(ws, 'Input.dispatchKeyEvent', { type: 'keyDown', key, code: 'Key' + key.toUpperCase(), text: key, windowsVirtualKeyCode: key.toUpperCase().charCodeAt(0) });
    await send(ws, 'Input.dispatchKeyEvent', { type: 'keyUp', key, code: 'Key' + key.toUpperCase(), windowsVirtualKeyCode: key.toUpperCase().charCodeAt(0) });
  }

  const letters = ['a', 'b', 'c', 'd'];
  for (const L of letters) {
    // 打当前字母（先读当前显示）
    const now = await evalJs(`document.querySelector('.center-letter')?.textContent || ''`);
    if (!now) { console.log('  页面已结束或异常，停止'); break; }
    await realKey(now);
    await sleep(750);
    const next = await evalJs(`document.querySelector('.center-letter')?.textContent || '(完成)'`);
    const logNow = await evalJs(`window.__speechLog`);
    console.log(`=== 真实按键 '${now}' 后 === 显示: ${JSON.stringify(next)}`);
    console.log('  语音日志:', JSON.stringify(logNow));
  }

  // 手势后的 speak 测试
  const gestureSpeak = await evalJs(`(async () => {
    if (!('speechSynthesis' in window)) return { skipped: true };
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance('z');
    u.lang = 'en-US';
    let started = false, errored = null;
    u.onstart = () => { started = true; };
    u.onerror = (e) => { errored = e.error; };
    window.speechSynthesis.speak(u);
    await new Promise(r => setTimeout(r, 1200));
    return { started, errored, speaking: window.speechSynthesis.speaking };
  })()`, true);
  console.log('=== 手势后手动 speak ===');
  console.log(JSON.stringify(gestureSpeak, null, 2));

  ws.close();
  chrome.kill();
}

main().catch((e) => { console.log('测试失败:', e.message); chrome.kill(); });
