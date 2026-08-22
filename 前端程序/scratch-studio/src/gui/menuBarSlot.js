/**
 * 在 Scratch 原生菜单栏里挖出一块属于平台的位置，并做品牌化（换标 + 染色）。
 *
 * 为什么是 DOM 手术而不是传 props：官方菜单栏只为标题、保存、分享、社区、账号
 * 开了槽，我们还有「提交作品」「判定状态」「任务要求」这些它压根没有的东西。
 * 这里创建一个真正的 `div` 插进它的 `main-menu` 里，再用 React portal 往里渲染
 * ——按钮是原生栏的**亲子节点**，不是拿 CSS 把两条栏画得像一条（那是 21f 明令
 * 禁止的伪装，两码事）。
 *
 * 三条自保规则：
 *  1. 选择器只认前缀 `menu-bar_menu-bar` / `menu-bar_main-menu`。类名尾巴上的
 *     `_x2Jqi` 是构建哈希，升级必变，认它等于给自己埋雷。
 *  2. 找不到锚点就返回 null，调用方退回独立横栏。升级 GUI 最坏是"退回双层"，
 *     不是白屏。
 *  3. 插入点选在分隔线之前；分隔线不在（版本改了结构）时 append 到末尾，
 *     位置不完美但功能不丢。
 */

const HEADER_SELECTOR = 'header[class*="menu-bar_menu-bar"]';
const MAIN_MENU_SELECTOR = 'div[class*="menu-bar_main-menu"]';
const DIVIDER_SELECTOR = 'div[class*="divider_divider"]';
const SLOT_ID = 'platform-bar-slot';
const STYLE_ID = 'platform-bar-style';

/** 原生菜单栏的高度（menu-bar.css 固定 48px）。栏内元素一律不许超过它。 */
export const MENU_BAR_HEIGHT = 48;

/**
 * 是否把整条菜单栏染成平台主色。
 *
 * 官方那条紫色（`$looks-secondary` = #855CD6）在 menu-bar.css 里是 Sass 变量，
 * 构建时已编译成字面量，**不是 CSS 变量**，没法用变量覆盖，只能加一条我们自己的
 * 规则盖掉（见 injectStyle）。合并之后整个页面只剩这一条栏，给它上自家品牌色是
 * 明牌不是伪装；要退回官方紫色，把这里改成 false，其余代码不用动。
 */
export const BRAND_MENU_BAR = true;

/** 找到原生菜单栏。找不到返回 null（GUI 还没挂载，或版本换了结构）。 */
export function findMenuBar () {
    return document.querySelector(HEADER_SELECTOR);
}

/**
 * 确保菜单栏里有我们的槽位，返回它；拿不到返回 null。
 * 幂等：已经存在就直接返回，不会插第二个。
 */
export function ensureMenuBarSlot () {
    const header = findMenuBar();
    if (!header) return null;
    const mainMenu = header.querySelector(MAIN_MENU_SELECTOR);
    if (!mainMenu) return null;

    const existing = mainMenu.querySelector(`#${SLOT_ID}`);
    if (existing) return existing;

    const slot = document.createElement('div');
    slot.id = SLOT_ID;
    // 槽位自己不换行、不撑高：原生栏 48px 是硬约束，撑破了就等于没合并。
    slot.style.display = 'flex';
    slot.style.alignItems = 'center';
    slot.style.gap = '8px';
    slot.style.flex = '1 1 auto';
    slot.style.minWidth = '0';
    slot.style.height = '100%';
    slot.style.overflow = 'hidden';
    slot.style.paddingInline = '8px';

    const divider = mainMenu.querySelector(DIVIDER_SELECTOR);
    mainMenu.insertBefore(slot, divider || null);
    return slot;
}

/**
 * 换掉猫标。`logo` prop 是死的，见 applyBranding 注释。
 *
 * 先预载再替换：平台的标在主站的 `/assets/` 下，Studio 独立开发服务（8602）直连时
 * 那个路径是 404。加载失败就保留原标——宁可还是猫，也不要一个裂图。
 */
let logoReady = null;

function swapLogo (src, alt) {
    const img = document.getElementById('logo_img');
    if (!img || !src) return;
    if (logoReady === null) {
        logoReady = new Promise(resolve => {
            const probe = new Image();
            probe.onload = () => resolve(true);
            probe.onerror = () => resolve(false);
            probe.src = src;
        });
    }
    logoReady.then(ok => {
        if (!ok) return;
        const target = document.getElementById('logo_img');
        if (!target) return;
        if (target.getAttribute('src') !== src) target.setAttribute('src', src);
        if (alt) target.setAttribute('alt', alt);
    });
}

function injectStyle () {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
/* 只认类名前缀，不认构建哈希（升级即变）。 */
${BRAND_MENU_BAR ? `${HEADER_SELECTOR} { background-color: var(--accent); }` : ''}

/* 标题输入框只换字体，**不要动颜色**。官方那套已经是对的：未聚焦时半透明白底 +
   白字（深色栏上清楚），聚焦时实白底 + 深字（project-title-input.css 的 :focus）。
   染成主色反而会让未聚焦态变成深绿压在半透明白上，更糊。 */
${HEADER_SELECTOR} input[class*="project-title-input_title-field"] {
    font-family: var(--font-ui);
}

/* 身份色带：教研 / 只读视图必须一眼能认出来。合并前靠整条栏的薄荷底色，
   合并后只剩这条 3px 顶边 + 栏内常驻标签（见 StudioBar 的 tone）。 */
html[data-studio-tone="admin"] ${HEADER_SELECTOR} { box-shadow: inset 0 3px 0 0 var(--warn); }
html[data-studio-tone="readonly"] ${HEADER_SELECTOR} { box-shadow: inset 0 3px 0 0 var(--muted); }

/* Scratch 15.0.1 没有关闭 Debug 的公开 prop。仅作业模式把含 debug-label 的原生
   按钮隐藏；教程按钮不受影响，且不改 node_modules。:has 已被项目支持的浏览器采用。 */
html[data-studio-hide-debug="true"] ${HEADER_SELECTOR} button:has(span[class*="debug-label"]) { display: none; }

/* 槽位里的按钮不参与 Scratch 的 hover 高亮，避免和菜单项混淆。 */
#${SLOT_ID} button { font-family: var(--font-ui); }
`;
    document.head.appendChild(style);
}

/**
 * 品牌化：换标 + 注入我们那几条样式。
 *
 * ⚠️ `<GUI logo={...}>` 是**死参数**：`gui.jsx:358` 确实把它传给了 MenuBar，
 * `menu-bar.jsx:673/721` 也声明了并给了默认值，但真正渲染那一行
 * （`menu-bar.jsx:336-345`）写死的是 `src={getScratchLogo(this.props.platform)}`，
 * 从头到尾没读过 `this.props.logo`。所以只能照它自己切换时空模式时的做法
 * （`menu-bar.jsx:228-238`）直接改那个 `<img id="logo_img">`。
 *
 * 换标不只是好看：包内 TRADEMARK 写明 Scratch 名称与猫标未经书面许可不得用于
 * 为衍生产品背书。自有平台的定制工作台，换成自家标更稳妥。
 */
export function applyBranding ({logoSrc, logoAlt} = {}) {
    injectStyle();
    swapLogo(logoSrc, logoAlt);
}

/** 设置身份色带。tone: 'student' | 'admin' | 'readonly' */
export function setStudioTone (tone) {
    if (tone === 'admin' || tone === 'readonly') {
        document.documentElement.dataset.studioTone = tone;
    } else {
        delete document.documentElement.dataset.studioTone;
    }
}

/** 仅在能力表明确要求时隐藏 Scratch 原生 Debug 入口。 */
export function setStudioDebugHidden (hidden) {
    if (hidden) {
        document.documentElement.dataset.studioHideDebug = 'true';
    } else {
        delete document.documentElement.dataset.studioHideDebug;
    }
}

export {SLOT_ID};
