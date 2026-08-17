import { createRouter, createWebHistory } from "vue-router";
import LobbyView from "./views/LobbyView.vue";
import Game24PlayView from "./views/Game24PlayView.vue";

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/", name: "lobby", component: LobbyView },
    { path: "/games/24", redirect: { name: "game24-play" } },
    { path: "/games/24/play", name: "game24-play", component: Game24PlayView },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
  scrollBehavior: () => ({ top: 0 }),
});
