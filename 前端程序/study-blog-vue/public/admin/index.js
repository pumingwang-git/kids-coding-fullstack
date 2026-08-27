import { adminRequest } from "./admin-api.js";
import { MENU, filterPageLinks, initLayout } from "./admin-layout.js";

const layoutReady = initLayout();

const $ = (id) => document.getElementById(id);
const number = (value) => (Number.isFinite(Number(value)) ? Number(value).toLocaleString("zh-CN") : "--");

function setText(id, value) {
  const node = $(id);
  if (node) node.textContent = value;
}

function blockedPageLabel(page) {
  for (const group of MENU) {
    if (group.page === page) return group.label;
    const child = group.children?.find((item) => item.page === page);
    if (child) return child.label;
  }
  return page;
}

function renderBlockedPageNotice() {
  const page = new URLSearchParams(location.search).get("blocked");
  if (!page) return;
  const notice = $("blockedPageNotice");
  if (!notice) return;
  notice.textContent = `「${blockedPageLabel(page)}」需要你当前角色没有的权限，已返回总览。`;
  notice.hidden = false;
}

function renderQueue({ questionPending, courseDraft, paperDraft, activeLinks }) {
  const items = [
    questionPending > 0
      ? { tone: "amber", title: `${questionPending} 道题目等待审核`, detail: "审核后才能进入正式题库。", href: "questions.html?status=pending", action: "去审核" }
      : { tone: "green", title: "题库审核队列已清空", detail: "可以继续录入新的练习题。", href: "questions.html", action: "新增试题" },
    courseDraft > 0
      ? { tone: "blue", title: `${courseDraft} 个课包仍是草稿`, detail: "补全内容后即可提交发布检查。", href: "courses.html?status=draft", action: "查看草稿" }
      : { tone: "green", title: "没有待发布的课包", detail: "已发布内容会持续展示在学习端。", href: "courses.html", action: "新建课包" },
    paperDraft > 0
      ? { tone: "violet", title: `${paperDraft} 份试卷正在准备`, detail: "完成配题后可以生成考试链接。", href: "papers.html?status=draft", action: "继续组卷" }
      : { tone: "green", title: "试卷发布状态正常", detail: activeLinks > 0 ? `当前有 ${activeLinks} 条活动考试链接。` : "可以创建一场新的考试。", href: "papers.html", action: "进入试卷" },
  ];
  $("dashboardQueue").innerHTML = items.map((item) => `<a class="dashboard-queue-item" href="${item.href}"><span class="queue-dot queue-dot-${item.tone}" aria-hidden="true"></span><span class="queue-copy"><b>${item.title}</b><small>${item.detail}</small></span><span class="queue-action">${item.action} <span aria-hidden="true">→</span></span></a>`).join("");
}

async function loadDashboard() {
  const refresh = $("refreshDashboard");
  refresh?.classList.add("is-loading");
  $("dashboardError").hidden = true;
  try {
    const me = await layoutReady;
    if (!me) return;
    const overview = await adminRequest("/dashboard/overview");
    const q = overview.questions;
    const p = overview.papers;
    const activeLinks = Number(overview.exam_links.active);
    setText("statCourses", number(overview.courses.total));
    setText("statCoursesMeta", `${number(overview.courses.published)} 个已上线`);
    setText("statQuestions", number(q.pending));
    setText("statQuestionsMeta", `${number(q.approved)} 道已发布`);
    setText("statPapers", number(p.published));
    setText("statPapersMeta", `${number(p.draft)} 份草稿待处理`);
    setText("statStudents", number(overview.students.total));
    setText("statLinks", number(activeLinks));
    setText("statLinksMeta", `${number(overview.exam_links.all)} 条链接总计`);
    renderQueue({ questionPending: Number(q.pending || 0), courseDraft: Number(overview.courses.draft), paperDraft: Number(p.draft || 0), activeLinks });
    filterPageLinks(me.allowed_pages);
  } catch (error) {
    $("dashboardError").textContent = error?.message || "数据加载失败，请稍后重试。";
    $("dashboardError").hidden = false;
    $("dashboardQueue").innerHTML = '<div class="dashboard-empty">暂时无法读取工作项，请点击右上角刷新重试。</div>';
  } finally {
    refresh?.classList.remove("is-loading");
  }
}

setText("dashboardDate", new Intl.DateTimeFormat("zh-CN", { dateStyle: "full" }).format(new Date()));
renderBlockedPageNotice();
$("refreshDashboard")?.addEventListener("click", loadDashboard);
loadDashboard();
