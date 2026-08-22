/**
 * 工作台操作条的共用样式。
 *
 * 2026-08-19 起，平台功能（保存 / 提交 / 判定 / 任务要求 …）不再自成一条横栏，
 * 而是渲染进 Scratch 原生菜单栏内部的槽位（见 `gui/menuBarSlot.js`）。所以这里
 * 的样式全部按"栏内元素"设计：
 *
 *  - 高度锁 32px，容器 48px 才不会被撑破；
 *  - 一律不换行（旧版 `flexWrap: 'wrap'` 是"两条杠变三条"的真凶：保存/提交/分享
 *    三条消息一起冒出来就自己折行）；
 *  - 文字白色。菜单栏底色不管是官方紫还是平台主色，都是深色底浅色字。
 *
 * 消息不再进栏，改走 `components/toast.js` 的浮层。
 *
 * 颜色一律走 `var(--*)` 令牌（定义在 index.html 的 :root，与 admin.css 同源）。
 */

/** 栏内控件统一高度。容器 48px − 上下各 8px 余量。 */
const CONTROL_HEIGHT = '32px';

/** 槽位里的一行。由 menuBarSlot 建的容器已是 flex，这里只管内容排布。 */
export const rowStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    minWidth: 0,
    flexWrap: 'nowrap'
};

/**
 * 找不到原生锚点时的退路：仍然是一条 48px 的独立横条，内容与栏内完全一样。
 * 保持深色底，栏内那套白字控件直接复用，不必为退路再养一套样式。
 */
export const fallbackBarStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    height: '48px',
    flexShrink: 0,
    padding: '0 12px',
    background: 'var(--accent)',
    color: '#fff',
    fontFamily: 'var(--font-ui)',
    fontSize: '13px',
    overflowX: 'auto',
    whiteSpace: 'nowrap'
};

/** 栏内标题（关卡名 / 作品名，只读展示用；自由创作走官方标题输入框）。 */
export const titleStyle = {
    fontWeight: 600,
    fontSize: '14px',
    color: '#fff',
    maxWidth: 'min(32ch, 28vw)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    flexShrink: 1,
    minWidth: 0
};

/** 圆角标签：判定状态、模式标识。 */
export function pillStyle (tone = 'neutral') {
    const tones = {
        neutral: {bg: 'rgba(255, 255, 255, 0.18)', fg: '#fff'},
        accent: {bg: 'rgba(255, 255, 255, 0.26)', fg: '#fff'},
        warn: {bg: 'var(--warn)', fg: 'var(--ink)'}
    };
    const {bg, fg} = tones[tone] || tones.neutral;
    return {
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: '3px 10px',
        borderRadius: '999px',
        fontSize: '12px',
        lineHeight: '18px',
        whiteSpace: 'nowrap',
        background: bg,
        color: fg,
        flexShrink: 0
    };
}

/** 次要动作：朴素文字按钮（保存、返回、更多…）。 */
export const btnStyle = {
    height: CONTROL_HEIGHT,
    padding: '0 12px',
    borderRadius: '6px',
    border: '1px solid rgba(255, 255, 255, 0.4)',
    background: 'transparent',
    color: '#fff',
    cursor: 'pointer',
    fontFamily: 'var(--font-ui)',
    fontSize: '13px',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    whiteSpace: 'nowrap',
    flexShrink: 0,
    boxSizing: 'border-box'
};

/**
 * 主按钮：**整条栏只允许有一个**。深色栏上用琥珀实心，视线一进来就知道点哪儿
 * （友商在蓝底上用黄色「发布作品」，同一个道理）。
 */
export const primaryBtnStyle = {
    ...btnStyle,
    background: 'var(--warn)',
    color: 'var(--ink)',
    borderColor: 'var(--warn)',
    fontWeight: 700
};

/** 更弱的一档：无边框，用于「更多」这类不该抢注意力的入口。 */
export const ghostBtnStyle = {
    ...btnStyle,
    border: '1px solid transparent',
    color: 'rgba(255, 255, 255, 0.92)'
};

/** 禁用态：不改布局，只降对比——按钮位置不能因为可点与否而跳动。 */
export const disabledStyle = {opacity: 0.45, cursor: 'not-allowed'};

/** 栏内小字说明（保存状态等）。长文案请走 title 属性或浮层，别塞进栏里。 */
export function noteStyle (tone = 'muted') {
    const colors = {
        muted: 'rgba(255, 255, 255, 0.8)',
        ok: '#fff',
        error: 'var(--warn)'
    };
    return {
        fontSize: '12px',
        color: colors[tone] || colors.muted,
        whiteSpace: 'nowrap',
        flexShrink: 0
    };
}

/** 浮层：独立于 Scratch GUI 的任何 stacking context，始终置顶。 */
export const popoverStyle = {
    position: 'fixed',
    top: '52px', // 菜单栏 48px + 4px 间隙
    right: '16px',
    background: 'var(--paper)',
    border: '1px solid var(--line)',
    borderRadius: '8px',
    boxShadow: '0 4px 16px rgba(34, 43, 40, 0.18)',
    padding: '12px',
    width: 'min(360px, calc(100vw - 32px))',
    maxHeight: 'calc(100vh - 76px)',
    overflowY: 'auto',
    fontFamily: 'var(--font-ui)',
    fontSize: '13px',
    color: 'var(--ink)',
    zIndex: 2147483647
};

/** 浮层内的小字（与栏内不同：浮层是浅底深字）。 */
export function popoverNoteStyle (tone = 'muted') {
    const colors = {muted: 'var(--muted)', ok: 'var(--accent)', error: 'var(--danger)'};
    return {fontSize: '12px', color: colors[tone] || colors.muted};
}
