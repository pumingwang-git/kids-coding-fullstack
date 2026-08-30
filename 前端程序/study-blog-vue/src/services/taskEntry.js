// 学生任务「点进去落到哪」的唯一映射。
//
// 四个任务页（学习任务总览 / 练一练 / 我的作业 / 考试）过去各拼各的路径，结果同一条
// Scratch 作业在总览里落到课时播放器、在作业页落到答卷页——两个落点，其中一个必错。
// 落点只按服务端下发的 `entry.kind` 分派，页面不再猜自己列表里装的是哪种任务。
//
// 为什么 Scratch 作业不直接跳工作台：工作台地址（studio_url）由服务端随课时块下发
// （components/lesson/blocks/BlockScratch.vue），任务列表里没有这个字段，前端自拼就是
// 又一处「自备契约」；何况直接进工作台会跳过「老师退回 / 判定中 / 反馈」这些只在块里
// 呈现的状态。回到课时里那一块，这些都由 BlockScratch 照常渲染。
export function taskEntryPath(item, { areaKey = "kids" } = {}) {
  const entry = item?.entry || {};
  if (item?.kind === "mistakes_review") return `/areas/${areaKey}/tasks/mistakes/review`;
  if (entry.kind === "mistake") return `/areas/${areaKey}/tasks/mistakes/${entry.mistake_id}`;
  if (entry.kind === "exam_link") return `/exam/${encodeURIComponent(entry.token)}`;
  if (entry.kind === "lesson_homework")
    return `/learn/${entry.lesson_id}/homework/${entry.block_id}`;
  // 课时播放器的 ?block= 深链（views/LessonPlayer.vue landingBlock）：顺序锁的块不吃这个
  // 参数，闸门绕不过去，所以这里可以放心带上。
  if (entry.kind === "lesson_scratch") return `/learn/${entry.lesson_id}?block=${entry.block_id}`;
  if (entry.lesson_id) return `/learn/${entry.lesson_id}`;
  if (item?.continue_lesson_id) return `/learn/${item.continue_lesson_id}`;
  return `/areas/${areaKey}/courses`;
}
