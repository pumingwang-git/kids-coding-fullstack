/**
 * 课程操作栏的共用样式。
 *
 * 为什么集中在这里：学生的保存/提交栏与教研的初始项目栏是同一条横条上的两种形态，
 * 分散写内联样式必然长出两套间距和两种按钮。放一处，改一次两边都跟着走。
 *
 * 颜色一律走 `var(--*)` 令牌（定义在 index.html 的 :root，与 admin.css 同源），
 * 不写十六进制：Studio 里再出现一套灰蓝色，页面就有第三种视觉语言了。
 *
 * 与 Scratch GUI 的关系见《21f Studio 界面集成决策记录》——两层刻意分明，
 * 不靠改色伪装成原生菜单。
 */

/** 顶部操作栏外壳。`variant: 'admin'` 用薄荷底色，一眼区分"这不是学生视图"。 */
export function barStyle (variant = 'student') {
    return {
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '10px 12px',
        padding: '8px 16px',
        background: variant === 'admin'
            ? 'color-mix(in srgb, var(--mint) 55%, var(--paper))'
            : 'var(--paper)',
        borderBottom: '1px solid var(--line)',
        fontFamily: 'var(--font-ui)',
        fontSize: '13px',
        color: 'var(--ink)',
        flexShrink: 0,
        minHeight: '44px'
    };
}

/** 关卡标题。`marginRight: auto` 把右侧按钮推到另一端。 */
export const titleStyle = {
    fontWeight: 600,
    marginRight: 'auto',
    // 长标题不该把按钮挤出屏幕：给它一个可收缩的上限，超出省略。
    maxWidth: 'min(42ch, 45vw)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap'
};

/** 圆角标签：判定状态、模式提示。 */
export function pillStyle (tone = 'neutral') {
    const tones = {
        neutral: {bg: 'color-mix(in srgb, var(--mint) 40%, var(--paper))', fg: 'var(--muted)'},
        accent: {bg: 'color-mix(in srgb, var(--accent) 12%, var(--paper))', fg: 'var(--accent)'},
        warn: {bg: 'color-mix(in srgb, var(--warn) 16%, var(--paper))', fg: 'var(--warn)'}
    };
    const {bg, fg} = tones[tone] || tones.neutral;
    return {
        padding: '2px 10px',
        borderRadius: '999px',
        fontSize: '12px',
        lineHeight: '18px',
        whiteSpace: 'nowrap',
        background: bg,
        color: fg,
        border: `1px solid ${tone === 'neutral' ? 'var(--line)' : 'transparent'}`
    };
}

export const btnStyle = {
    padding: '6px 16px',
    borderRadius: '6px',
    border: '1px solid var(--line)',
    background: 'var(--paper)',
    color: 'var(--ink)',
    cursor: 'pointer',
    fontFamily: 'var(--font-ui)',
    fontSize: '13px',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    whiteSpace: 'nowrap',
    // 触摸目标：各 Bar 组件中按钮高度一致，视觉上不突兀。
    minHeight: '36px',
    boxSizing: 'border-box'
};

export const primaryBtnStyle = {
    ...btnStyle,
    background: 'var(--accent)',
    color: 'var(--paper)',
    borderColor: 'var(--accent)'
};

export const ghostBtnStyle = {...btnStyle, border: 'none', background: 'transparent', color: 'var(--muted)'};

/** 禁用态：不改布局，只降对比——按钮位置不能因为可点与否而跳动。 */
export const disabledStyle = {opacity: 0.45, cursor: 'not-allowed'};

export function noteStyle (tone = 'muted') {
    const colors = {muted: 'var(--muted)', ok: 'var(--accent)', error: 'var(--danger)'};
    return {fontSize: '12px', color: colors[tone] || colors.muted};
}

/** 浮层：独立于 Scratch GUI 的任何 stacking context，始终置顶。 */
export const popoverStyle = {
    position: 'fixed',
    top: '60px',
    right: '16px',
    background: 'var(--paper)',
    border: '1px solid var(--line)',
    borderRadius: '8px',
    boxShadow: '0 4px 16px rgba(34, 43, 40, 0.12)',
    padding: '12px',
    width: 'min(360px, calc(100vw - 32px))',
    maxHeight: 'calc(100vh - 76px)',
    overflowY: 'auto',
    fontFamily: 'var(--font-ui)',
    color: 'var(--ink)',
    zIndex: 2147483647
};
