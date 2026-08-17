// CDP 实测脚本 v3：全程走完字母乐园（26 字母 + 10 单词），
// hook speechSynthesis.speak 统计调用/开始/错误，观察自动跳转是否全程正常
import { spawn } from 'node:child_process';

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const URL = 'http://127.0.0.1:8603/?age=3-6&mode=letter';

const chrome = spawn(CHROME, [
  '--headless=new', '--disable-gpu', '--no-first-run',
  '--remote-debugging-port=9224',
  '--user-data-dir=C:/Users/asus/.workbuddy/binaries/node/workspace/.chrome-test-profile3',
  URL
], { stdio: 'ignore' });

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
async function getJson(url) { return (await fetch(url)).json(); }
async function connectWs(url) {
  const ws = new WebSocket(url);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
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
  try { targets = await getJson('http://127.0.0.1:9224/json'); }
  catch (e) { console.log('CDP 连接失败:', e.message); chrome.kill(); return; }
  const page = targets.find((t) => t.type === 'page');
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
  async function realKey(key) {
    await send(ws, 'Input.dispatchKeyEvent', { type: 'keyDown', key, code: 'Key' + key.toUpperCase(), text: key, windowsVirtualKeyCode: key.toUpperCase().charCodeAt(0) });
    await send(ws, 'Input.dispatchKeyEvent', { type: 'keyUp', key, code: 'Key' + key.toUpperCase(), windowsVirtualKeyCode: key.toUpperCase().charCodeAt(0) });
  }

  // hook speechSynthesis.speak
  await evalJs(`(() => {
    window.__speakCount = 0; window.__startCount = 0; window.__errLog = [];
    if ('speechSynthesis' in window) {
      const orig = window.speechSynthesis.speak.bind(window.speechSynthesis);
      window.speechSynthesis.speak = (u) => {
        window.__speakCount++;
        u.addEventListener('start', () => { window.__startCount++; });
        u.addEventListener('error', (e) => { window.__errLog.push(e.error); });
        orig(u);
      };
    }
    return 'hooked';
  })()`);

  // 先给一次真实手势，解锁 autoplay（模拟用户第一次按键后）
  const first = await evalJs(`document.querySelector('.center-letter')?.textContent || ''`);
  console.log('初始字母:', JSON.stringify(first));
  if (first) { await realKey(first); await sleep(650); }

  const results = [];
  let phase = 'letter';
  let letterDone = 0, wordDone = 0;
  let guard = 0;

  while (guard++ < 200) {
    const state = await evalJs(`(() => {
      const letterEl = document.querySelector('.center-letter');
      const zhEl = document.querySelector('.center-zh');
      const tip = document.querySelector('.lp-tip');
      const done = document.querySelector('.lp-done');
      if (done) return { done: true };
      const txt = letterEl ? letterEl.textContent.trim() : '';
      return { txt, isWord: !!zhEl, tip: tip ? tip.textContent : '' };
    })()`);

    if (state.done) { results.push({ event: 'FINISHED' }); break; }
    if (state.__error) { results.push({ event: 'ERR', ...state }); break; }

    const target = state.txt;
    if (!target) { results.push({ event: 'EMPTY', ...state }); break; }

    if (state.isWord) {
      if (phase !== 'word') { phase = 'word'; results.push({ event: '→WORD阶段', word: target }); }
      // 逐个字母打，全部正确
      for (const ch of target.toLowerCase()) {
        await realKey(ch);
        await sleep(80);
      }
      wordDone++;
      results.push({ event: 'word#' + wordDone + ' 打完', word: target });
      await sleep(750); // 等跳转
    } else {
      if (phase !== 'letter') phase = 'letter';
      letterDone++;
      if (letterDone <= 28) results.push({ event: 'letter#' + letterDone, letter: target });
      await realKey(target.toLowerCase());
      await sleep(650); // 等跳转
    }
  }

  await sleep(600);
  const speech = await evalJs(`({ speak: window.__speakCount, start: window.__startCount, errors: window.__errLog })`);
  console.log('=== 全程结果 ===');
  for (const r of results) console.log(' ', JSON.stringify(r));
  console.log('=== speech 统计 ===');
  console.log('speak调用:', speech.speak, ' start事件:', speech.start, ' 错误:', JSON.stringify(speech.errors));

  ws.close();
  chrome.kill();
}

main().catch((e) => { console.log('测试失败:', e.message); chrome.kill(); });
