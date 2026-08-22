// @vitest-environment jsdom
// Scratch 工作台把平台功能（保存 / 提交 / 判定 / 任务要求…）渲染进**原生菜单栏内部**，
// 页面上只剩一条 48px 的栏。锚点是靠类名前缀找的 DOM 手术，这里守三件事：
//
//  1. 找得到锚点时，槽位插在 main-menu 里、分隔线之前；
//  2. **找不到锚点时必须返回 null** —— 上层据此退回独立横条。这条是降级开关，
//     选择器一旦写宽（比如退化成 `header`），升级后就会插进错误的地方而不是降级；
//  3. 幂等：重复调用不会插出第二个槽位（StudioBar 每秒轮询一次）。
//
// 选择器只认前缀（`menu-bar_menu-bar`），不认构建哈希（`_x2Jqi` 升级必变）。
import { beforeEach, describe, expect, it } from "vitest";
import {
  ensureMenuBarSlot,
  findMenuBar,
  applyBranding,
  setStudioTone,
  setStudioDebugHidden,
  MENU_BAR_HEIGHT,
} from "../../scratch-studio/src/gui/menuBarSlot.js";

/** 照抄 scratch-gui 15.0.1 渲染出来的真实结构（类名含构建哈希）。 */
function mountMenuBar({ withDivider = true, headerClass, mainMenuClass } = {}) {
  document.body.innerHTML = `
    <div id="root">
      <div>
        <header class="${headerClass ?? "gui_menu-bar-position_pGQv1 menu-bar_menu-bar_x2Jqi box_box_bP3Aq"}">
          <div class="${mainMenuClass ?? "menu-bar_main-menu_A6H+H"}">
            <div class="menu-bar_file-group_bTVDk"><img id="logo_img" alt="Scratch" src="/scratch-logo.svg" /></div>
            <div class="menu-bar_menu-bar-item_NKeCD"></div>
            ${withDivider ? '<div class="divider_divider_1_Xzq menu-bar_divider_+COr1"></div>' : ""}
            <div class="menu-bar_file-group_bTVDk"></div>
          </div>
          <div class="menu-bar_account-info-group_dJSjn"></div>
        </header>
      </div>
    </div>`;
}

beforeEach(() => {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
  delete document.documentElement.dataset.studioTone;
  delete document.documentElement.dataset.studioHideDebug;
});

describe("菜单栏槽位", () => {
  it("插在 main-menu 内、分隔线之前", () => {
    mountMenuBar();
    const slot = ensureMenuBarSlot();
    expect(slot).toBeTruthy();
    const mainMenu = document.querySelector('div[class*="menu-bar_main-menu"]');
    expect(slot.parentElement).toBe(mainMenu);
    const kids = Array.from(mainMenu.children);
    const divider = mainMenu.querySelector('div[class*="divider_divider"]');
    expect(kids.indexOf(slot)).toBeLessThan(kids.indexOf(divider));
  });

  it("幂等：轮询重复调用只有一个槽位", () => {
    mountMenuBar();
    const first = ensureMenuBarSlot();
    const second = ensureMenuBarSlot();
    expect(second).toBe(first);
    expect(document.querySelectorAll("#platform-bar-slot").length).toBe(1);
  });

  it("没有分隔线（结构变了）时退而求其次，追加到末尾", () => {
    mountMenuBar({ withDivider: false });
    const slot = ensureMenuBarSlot();
    const mainMenu = document.querySelector('div[class*="menu-bar_main-menu"]');
    expect(slot).toBeTruthy();
    expect(mainMenu.lastElementChild).toBe(slot);
  });

  // —— 降级闸：下面两条一旦变绿失败，说明选择器被写宽了 ——
  it("菜单栏类名对不上时返回 null（上层据此退回独立横条）", () => {
    mountMenuBar({ headerClass: "upgraded_top-bar_9xQ2" });
    expect(findMenuBar()).toBeNull();
    expect(ensureMenuBarSlot()).toBeNull();
    expect(document.querySelector("#platform-bar-slot")).toBeNull();
  });

  it("只有 header、没有 main-menu 时同样返回 null", () => {
    mountMenuBar({ mainMenuClass: "renamed_inner_container" });
    expect(findMenuBar()).not.toBeNull();
    expect(ensureMenuBarSlot()).toBeNull();
  });

  it("页面上压根没有编辑器时不炸", () => {
    expect(() => ensureMenuBarSlot()).not.toThrow();
    expect(ensureMenuBarSlot()).toBeNull();
  });
});

describe("品牌化", () => {
  it("样式只注入一次", () => {
    mountMenuBar();
    applyBranding();
    applyBranding();
    expect(document.querySelectorAll("#platform-bar-style").length).toBe(1);
  });

  it("注入的规则认类名前缀，不认构建哈希", () => {
    mountMenuBar();
    applyBranding();
    const css = document.getElementById("platform-bar-style").textContent;
    expect(css).toContain('header[class*="menu-bar_menu-bar"]');
    expect(css).not.toContain("_x2Jqi");
  });

  it("身份色带：教研 / 只读上标，学生态清掉", () => {
    setStudioTone("admin");
    expect(document.documentElement.dataset.studioTone).toBe("admin");
    setStudioTone("readonly");
    expect(document.documentElement.dataset.studioTone).toBe("readonly");
    setStudioTone("student");
    expect(document.documentElement.dataset.studioTone).toBeUndefined();
  });

  it("作业模式可只隐藏 Debug，不影响教程入口", () => {
    mountMenuBar();
    applyBranding();
    setStudioDebugHidden(true);
    expect(document.documentElement.dataset.studioHideDebug).toBe("true");
    const css = document.getElementById("platform-bar-style").textContent;
    expect(css).toContain('button:has(span[class*="debug-label"])');
    expect(css).not.toContain('tutorials-button { display: none');
    setStudioDebugHidden(false);
    expect(document.documentElement.dataset.studioHideDebug).toBeUndefined();
  });

  it("栏高常量与官方 menu-bar.css 一致（48px）", () => {
    expect(MENU_BAR_HEIGHT).toBe(48);
  });
});
