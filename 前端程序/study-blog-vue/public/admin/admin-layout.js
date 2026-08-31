// 后台管理共享布局：侧边菜单（一级/二级）+ 顶栏（面包屑/管理员/退出）。
// 所有后台页面只需：
//   <div id="sidebar"></div><div id="topbar"></div>
//   <script type="module">import { initLayout } from "./admin-layout.js"; initLayout();</script>
//
// 菜单命名规范：
//   一级 = 业务域（总览/配题/配课/运营）
//   二级 = 业务对象 + 「管理/统计」后缀（名词，不用动词）
//   动作类页面（新建/编辑表单）不进菜单，由列表页按钮进入。
import { adminLogout, adminMe, adminRequest } from "./admin-api.js";

export const MENU = [
  { key: "dashboard", label: "总览", icon: "总", page: "index.html", crumb: "总览 / 管理总览" },
  {
    key: "question",
    label: "配题",
    icon: "题",
    children: [
      { label: "题库管理", page: "questions.html", crumb: "配题 / 题库管理" },
      { label: "试卷管理", page: "papers.html", crumb: "配题 / 试卷管理" },
      { label: "考试链接", page: "exam-links.html", crumb: "配题 / 考试链接" },
    ],
  },
  {
    key: "course",
    label: "配课",
    icon: "课",
    children: [
      { label: "课包管理", page: "courses.html", crumb: "配课 / 课包管理" },
      { label: "学习目录", page: "learning-catalog.html", crumb: "配课 / 学习目录" },
      { label: "内容编排", page: "nodes.html", crumb: "配课 / 内容编排" },
      { label: "资料管理", page: "materials.html", crumb: "配课 / 资料管理" },
      { label: "视频管理", page: "videos.html", crumb: "配课 / 视频管理" },
    ],
  },
  {
    key: "ops",
    label: "运营",
    icon: "营",
    children: [
      { label: "学员管理", page: "students.html", crumb: "运营 / 学员管理" },
      { label: "课程开通", page: "enrollments.html", crumb: "运营 / 课程开通" },
      { label: "班级管理", page: "classes.html", crumb: "运营 / 班级管理" },
      { label: "教学工作台", page: "teaching.html", crumb: "运营 / 教学工作台" },
      { label: "答疑工作台", page: "help-desk.html", crumb: "运营 / 答疑工作台" },
      { label: "成绩统计", page: "reports.html", crumb: "运营 / 成绩统计" },
      { label: "课时作业成绩", page: "homework-results.html", crumb: "运营 / 课时作业成绩" },
      { label: "账号与角色", page: "accounts.html", crumb: "运营 / 账号与角色" },
      { label: "审计日志", page: "audit-logs.html", crumb: "运营 / 审计日志" },
    ],
  },
];

function currentPage() {
  return (location.pathname.split("/").pop() || "index.html").split("?")[0];
}

export function initLayout() {
  const sidebar = document.getElementById("sidebar");
  const topbar = document.getElementById("topbar");
  if (sidebar) renderSidebar(sidebar);
  if (topbar) {
    renderTopbar(topbar);
    return loadAdmin(topbar, sidebar);
  }
  return Promise.resolve(null);
}

function renderSidebar(sidebar) {
  const page = currentPage();
  let html = '<a class="brand" href="index.html"><i>LP</i><span>学习平台<small>运营工作台</small></span></a><nav class="menu">';
  for (const group of MENU) {
    if (group.children) {
      const open = group.children.some((child) => child.page === page) ? " open" : "";
      html += `<div class="menu-group${open}"><div class="menu-parent"><i class="menu-icon">${group.icon}</i>${group.label}<span class="arrow">⌄</span></div><div class="menu-children">`;
      for (const child of group.children) {
        html += `<a class="menu-item${child.page === page ? " active" : ""}" data-menu-page="${child.page}" hidden href="${child.page}">${child.label}</a>`;
      }
      html += "</div></div>";
    } else {
      html += `<a class="menu-item single${group.page === page ? " active" : ""}" data-menu-page="${group.page}" hidden href="${group.page}"><i class="menu-icon">${group.icon}</i>${group.label}</a>`;
    }
  }
  html += '</nav><div class="sidebar-foot"><span>教学内容运营</span><small>v1.0</small></div>';
  sidebar.innerHTML = html;

  // 一级菜单展开/收起
  sidebar.querySelectorAll(".menu-parent").forEach((parent) => {
    parent.addEventListener("click", () => {
      parent.parentElement.classList.toggle("open");
    });
  });
}

function applyMenuFilter(sidebar, menus) {
  const allowed = new Set(Array.isArray(menus) ? menus : []);
  sidebar.querySelectorAll("[data-menu-page]").forEach((item) => {
    item.hidden = !allowed.has(item.dataset.menuPage);
  });
  sidebar.querySelectorAll(".menu-group").forEach((group) => {
    const visible = group.querySelector("[data-menu-page]:not([hidden])");
    group.hidden = !visible;
  });
}

export function filterPageLinks(allowedPages) {
  const allowed = new Set(Array.isArray(allowedPages) ? allowedPages : []);
  document.querySelectorAll('a[href$=".html"], a[href*=".html?"]').forEach((link) => {
    const page = (link.getAttribute("href") || "").split("?")[0].split("/").pop();
    if (page && !allowed.has(page) && page !== "login.html") link.hidden = true;
  });
}

function renderTopbar(topbar) {
  const page = currentPage();
  const active = findActive(page);
  const crumb = active ? active.crumb : "后台管理";
  topbar.innerHTML = `
    <div class="crumb"><span>学习平台</span><b>${crumb}</b></div>
    <div class="topbar-right">
      <a class="btn-text topbar-notifications" href="notifications.html" aria-label="通知">通知<span id="adminNotificationCount" class="topbar-notification-count" hidden></span></a>
      <span class="muted" id="adminName">加载中…</span>
      <button class="btn-text" id="logoutBtn" type="button">退出登录</button>
    </div>`;
  topbar.querySelector("#logoutBtn").addEventListener("click", async () => {
    try {
      await adminLogout();
    } finally {
      location.href = "login.html";
    }
  });
}

function findActive(page) {
  for (const group of MENU) {
    if (group.page === page) return group;
    if (group.children) {
      const child = group.children.find((item) => item.page === page);
      if (child) return child;
    }
  }
  return null;
}

async function loadAdmin(topbar, sidebar) {
  try {
    const me = await adminMe();
    if (me.must_change_password && currentPage() !== "password-change.html") {
      location.replace("password-change.html");
      return me;
    }
    const allowedPages = new Set(me.allowed_pages || []);
    if (!allowedPages.has(currentPage())) {
      location.replace("index.html?blocked=" + encodeURIComponent(currentPage()));
      return me;
    }
    const name = topbar.querySelector("#adminName");
    if (name) name.textContent = `${me.display_name}（${me.role_label || me.role}）`;
    try {
      const unread = await adminRequest("/notifications/unread-count");
      const badge = topbar.querySelector("#adminNotificationCount");
      const count = Number(unread?.count || 0);
      if (badge && count > 0) {
        badge.textContent = count > 99 ? "99+" : String(count);
        badge.hidden = false;
      }
    } catch {
      // The link remains usable when the optional unread count is unavailable.
    }
    if (sidebar) applyMenuFilter(sidebar, me.menus);
    filterPageLinks(me.allowed_pages);
    document.dispatchEvent(new CustomEvent("admin:ready", { detail: me }));
    return me;
  } catch {
    // 未登录 → 回登录页，登录后回到当前页
    location.href = `login.html?next=${encodeURIComponent(location.pathname)}`;
    return null;
  }
}
