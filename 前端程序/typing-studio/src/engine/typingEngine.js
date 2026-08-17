// TypingEngine · 打字引擎
// 业务逻辑改写自开源项目 Monkeytype（GPL-3.0）的字符级对比与统计思路，
// 不引入其代码，仅复用「逐字符比对 / 错误标记 / WPM 统计」的行业通行做法。
//
// 两种输入策略：
//  - strict（金山打字风格）：打错必须退格改正，正确才推进 —— 警察抓小偷/字母吃掉
//  - flow（Monkeytype 风格）：打错标红继续往后打，结束时按准确率结算 —— 段落马拉松
export class TypingEngine {
  constructor(target, options = {}) {
    this.target = target;
    this.strategy = options.strategy || 'strict';
    this.onUpdate = options.onUpdate || null;

    this.cursor = 0;          // 已推进到的位置
    this.typedChars = [];     // 已输入字符（与 cursor 对齐）
    this.charStates = [];     // 'correct' | 'incorrect' | 'missing'
    this.startTime = null;
    this.endTime = null;
    this.errorCount = 0;
    this.streak = 0;          // 当前连续正确
    this.maxStreak = 0;
    for (let i = 0; i < target.length; i++) this.charStates.push('missing');
  }

  get finished() {
    return this.cursor >= this.target.length;
  }

  get progress() {
    return this.target.length ? this.cursor / this.target.length : 1;
  }

  type(char) {
    if (this.finished) return { ok: false, finished: true };
    if (this.startTime == null) this.startTime = Date.now();

    const expected = this.target[this.cursor];
    const ok = char.toLowerCase() === expected.toLowerCase();

    if (this.strategy === 'strict') {
      if (ok) {
        this.typedChars[this.cursor] = char;
        this.charStates[this.cursor] = 'correct';
        this.cursor++;
        this.streak++;
        this.maxStreak = Math.max(this.maxStreak, this.streak);
      } else {
        this.errorCount++;
        this.streak = 0;
      }
    } else {
      // flow：无论对错都推进，错字符标红
      this.typedChars[this.cursor] = char;
      this.charStates[this.cursor] = ok ? 'correct' : 'incorrect';
      if (ok) {
        this.streak++;
        this.maxStreak = Math.max(this.maxStreak, this.streak);
      } else {
        this.errorCount++;
        this.streak = 0;
      }
      this.cursor++;
    }

    if (this.finished) this.endTime = Date.now();
    this.emit();
    return { ok, finished: this.finished };
  }

  backspace() {
    if (this.cursor <= 0) return;
    this.cursor--;
    this.typedChars.length = this.cursor;
    this.charStates[this.cursor] = 'missing';
    this.emit();
  }

  reset(target) {
    if (target) this.target = target;
    this.cursor = 0;
    this.typedChars = [];
    this.charStates = this.target.split('').map(() => 'missing');
    this.startTime = null;
    this.endTime = null;
    this.errorCount = 0;
    this.streak = 0;
    this.maxStreak = 0;
    this.emit();
  }

  // WPM = 正确字符数 / 5（一个单词按 5 字符计）/ 分钟
  get stats() {
    const elapsedMs = (this.endTime || Date.now()) - (this.startTime || Date.now());
    const minutes = elapsedMs / 60000;
    const correct = this.charStates.filter((s) => s === 'correct').length;
    const wpm = minutes > 0 ? Math.round(correct / 5 / minutes) : 0;
    const totalTyped = correct + this.errorCount;
    const accuracy = totalTyped > 0 ? Math.round((correct / totalTyped) * 100) : 100;
    return {
      wpm,
      accuracy,
      correct,
      errors: this.errorCount,
      streak: this.streak,
      maxStreak: this.maxStreak,
      elapsedMs,
      progress: this.progress
    };
  }

  emit() {
    if (this.onUpdate) this.onUpdate(this);
  }
}
