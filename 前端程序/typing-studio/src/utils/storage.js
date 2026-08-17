// localStorage 成绩/徽章存取：按游戏维度记录最佳成绩与最近成绩。
// 二期接入学生账号后，可改为上报后端（复用学生端成绩体系）。
const KEY = 'typing-studio-progress';

export function loadProgress() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {};
  }
}

// recordGame('spell', { wpm: 42, accuracy: 96 })
// 返回更新后的该游戏记录：{ last, best, count }
export function recordGame(game, stats) {
  const all = loadProgress();
  const prev = all[game] || {};
  const primary = stats.primaryKey || 'wpm';
  const score = stats[primary] || 0;
  const record = {
    last: stats,
    best: prev.best && prev.best[primary] >= score ? prev.best : stats,
    count: (prev.count || 0) + 1
  };
  all[game] = record;
  try {
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    /* 隐私模式等场景静默失败 */
  }
  return record;
}

export function getRecord(game) {
  return loadProgress()[game] || null;
}
