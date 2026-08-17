// 后台管理共享布局：侧边菜单（一级/二级）+ 顶栏（面包屑/管理员/退出）。
// 所有后台页面只需：
//   <div id="sidebar"></div><div id="topbar"></div>
//   <script type="module">import { initLayout } from "./admin-layout.js"; initLayout();</script>
//
// 菜单命名规范：
//   一级 = 业务域（总览/配题/配课/运营）
//   二级 = 业务对象 + 「管理/统计」后缀（名词，不用动词）
//   动作类页面（新建/编辑表单）不进菜单，由列表页按钮进入。
import { adminLogout, adminMe } from "./admin-api.js";

export const MENU = [
  { key: "dashboard", label: "总览", icon: "📊", page: "index.html", crumb: "总览 / 管理总览" },
  {
    key: "question",
    label: "配题",
    icon: "📚",
    children: [
      { label: "题库管理", page: "questions.html", crumb: "配题 / 题库管理" },
      { label: "试卷管理", page: "papers.html", crumb: "配题 / 试卷管理" },
      { label: "考试链接", page: "exam-links.html", crumb: "配题 / 考试链接" },
    ],
  },
  {
    key: "course",
    label: "配课",
    icon: "🎬",
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
    icon: "🛠",
    children: [
      { label: "学员管理", page: "students.html", crumb: "运营 / 学员管理" },
      { label: "成绩统计", page: "reports.html", crumb: "运营 / 成绩统计" },
      { label: "课时作业成绩", page: "homework-results.html", crumb: "运营 / 课时作业成绩" },
      // superOnly：ADR-001 §2.4 规定变更 AdminUser.role 仅限 super_admin，
      // 非超管连入口都不该看到。隐藏入口只是体验，后端仍然独立 403。
      { label: "账号与角色", page: "accounts.html", crumb: "运营 / 账号与角色", superOnly: true },
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
    loadAdmin(topbar, sidebar);
  }
}

function renderSidebar(sidebar) {
  const page = currentPage();
  let html = '<div class="brand"><i>◆</i> 学习平台 · 后台</div><nav class="menu">';
  for (const group of MENU) {
    if (group.children) {
      const open = group.children.some((child) => child.page === page) ? " open" : "";
      html += `<div class="menu-group${open}"><div class="menu-parent">${group.icon} ${group.label} <span class="arrow">▾</span></div><div class="menu-children">`;
      for (const child of group.children) {
        // 默认渲染成 hidden，避免非超管在 /me 返回前先看到一帧授权入口。
        const gated = child.superOnly ? " data-super-only hidden" : "";
        html += `<a class="menu-item${child.page === page ? " active" : ""}"${gated} href="${child.page}">${child.label}</a>`;
      }
      html += "</div></div>";
    } else {
      html += `<a class="menu-item single${group.page === page ? " active" : ""}" href="${group.page}">${group.icon} ${group.label}</a>`;
    }
  }
  html += '</nav><div class="sidebar-foot">学习平台后台 · 配题建设中</div>';
  sidebar.innerHTML = html;

  // 一级菜单展开/收起
  sidebar.querySelectorAll(".menu-parent").forEach((parent) => {
    parent.addEventListener("click", () => {
      parent.parentElement.classList.toggle("open");
    });
  });
}

function renderTopbar(topbar) {
  const page = currentPage();
  const active = findActive(page);
  const crumb = active ? active.crumb : "后台管理";
  topbar.innerHTML = `
    <div class="crumb">后台管理 / <b>${crumb}</b></div>
    <div class="topbar-right">
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
    const name = topbar.querySelector("#adminName");
    if (name) name.textContent = `${me.display_name}（${me.role}）`;
    if (me.can_manage_admin_roles && sidebar) {
      sidebar.querySelectorAll("[data-super-only]").forEach((item) => {
        item.hidden = false;
      });
    }
  } catch {
    // 未登录 → 回登录页，登录后回到当前页
    location.href = `login.html?next=${encodeURIComponent(location.pathname)}`;
  }
}
