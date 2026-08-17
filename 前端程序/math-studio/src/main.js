import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./styles.css";
import { resolveSession } from "./platform/session";

export async function bootstrap() {
  const container = document.getElementById("app");
  if (!container) return;

  const session = await resolveSession();
  if (!session.user) {
    if (session.reason === "unauthenticated") {
      const next = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      // math-studio runs on its own Vite port in development, while auth belongs
      // to the main learning platform. Production is same-origin; local dev can
      // override the host with VITE_AUTH_ORIGIN when the shell uses another port.
      const authOrigin = import.meta.env.VITE_AUTH_ORIGIN
        || (import.meta.env.DEV ? "http://localhost:5173" : window.location.origin);
      const authUrl = new URL("/auth", authOrigin);
      authUrl.searchParams.set("next", next);
      window.location.replace(authUrl.toString());
      return;
    }
    container.innerHTML = `
      <main class="boot-error">
        <div class="boot-error__mark" aria-hidden="true">24</div>
        <h1>暂时连不上学习平台</h1>
        <p>请检查网络后重试。已经在这台设备登录过时，离线记录仍会保留。</p>
        <button type="button" onclick="window.location.reload()">重新连接</button>
      </main>`;
    return;
  }

  createApp(App).use(router).mount(container);
}

if (import.meta.env.MODE !== "test") void bootstrap();
