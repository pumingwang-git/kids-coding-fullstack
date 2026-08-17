const routes = {
  "#/": { screen: "landing", title: "学习系统 | 汪蒲明" },
  "#/login": { screen: "auth", title: "登录 | 学习系统" },
  "#/courses": { screen: "courses", title: "课程列表 | 学习系统" },
  "#/courses/html-basics": { screen: "lesson", title: "HTML 练习 | 学习系统" },
};

const screens = document.querySelectorAll("[data-screen]");
const navLinks = document.querySelectorAll("[data-route]");
const themeButton = document.querySelector(".theme-toggle");

function renderRoute() {
  const route = routes[window.location.hash] || routes["#/"];
  document.title = route.title;

  screens.forEach((screen) => {
    screen.hidden = screen.dataset.screen !== route.screen;
  });

  navLinks.forEach((link) => {
    const isActive = link.dataset.route === window.location.hash;
    link.classList.toggle("active", isActive);
    link.setAttribute("aria-current", isActive ? "page" : "false");
  });

  window.scrollTo({ top: 0, behavior: "auto" });
}

if (!window.location.hash || !routes[window.location.hash]) {
  window.location.hash = "/";
}

window.addEventListener("hashchange", renderRoute);
renderRoute();

document.querySelectorAll(".auth-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    const isRegister = tab.dataset.auth === "register";
    document
      .querySelectorAll(".auth-tab")
      .forEach((item) => item.classList.toggle("active", item === tab));
    document.querySelector("[data-auth-title]").textContent = isRegister
      ? "创建你的账号"
      : "欢迎回来";
    document.querySelector("[data-auth-copy]").textContent = isRegister
      ? "注册后，就可以从第一节课开始慢慢积累。"
      : "输入账号和密码，继续上一次的学习。";
    document.querySelector("[data-auth-submit]").innerHTML = isRegister
      ? "创建账号 <span>↗</span>"
      : "登录并继续 <span>↗</span>";
    document.querySelector("[data-auth-footnote]").textContent = isRegister
      ? "已经有账号？可以切换回登录页看看。"
      : "还没有账号？可以切换到注册页看看。";
  });
});

document.querySelector(".auth-form").addEventListener("submit", (event) => {
  event.preventDefault();
});

const savedTheme = localStorage.getItem("practice-theme");
if (savedTheme === "dark") document.body.classList.add("dark");

themeButton.addEventListener("click", () => {
  const isDark = document.body.classList.toggle("dark");
  localStorage.setItem("practice-theme", isDark ? "dark" : "light");
});
