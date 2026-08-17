/**
 * 教研在 Studio 里录制的两种目标：初始项目 / 示范项目。
 *
 * 为什么是一张表而不是组件里的 if-else：两条目标的载入地址、写回地址、可写判据、
 * 已存在判据各不相同（示范项目的下载地址甚至在另一个 payload 段里），散在
 * StudioApp 和 AuthoringBar 两处判断，迟早出现"点了示范项目的保存却写进初始项目"。
 * 表在这里，两个调用方查同一份。
 *
 * 注意 `demo` 的 `loadUrl` 取自 `authoring.demo_url` 而不是 `challenge.demo_url`：
 * `challenge` 段的形状要与学生端 payload 对齐，而学生端永远不会有示范项目的下载地址
 * （见 21g 交接文档 §8.2）。
 */

export const AUTHORING_TARGETS = {
    starter: {
        key: 'starter',
        label: '初始项目',
        // 顶栏文案：老师必须一眼看出自己正在录哪一份，不能只靠记得点了哪个按钮。
        recordingLabel: '正在录制：初始项目',
        filename: 'starter.sb3',
        savedNote: '已存为本关初始项目，学生下次进入将从这一版开始。',
        reloadedNote: '已载入服务器上的当前初始项目。',
        emptyHint: '本关还没有初始项目',
        loadUrl: ctx => (ctx.challenge && ctx.challenge.starter_url) || null,
        writeUrl: ctx => (ctx.authoring && ctx.authoring.starter_write_url) || null,
        canWrite: ctx => Boolean(ctx.authoring && ctx.authoring.can_write_starter),
        exists: ctx => Boolean(ctx.challenge && ctx.challenge.has_starter)
    },
    demo: {
        key: 'demo',
        label: '示范项目',
        recordingLabel: '正在录制：示范项目',
        filename: 'demo.sb3',
        savedNote: '已存为本关示范项目，学生提交并拿到结果后可只读查看。',
        reloadedNote: '已载入服务器上的当前示范项目。',
        emptyHint: '本关还没有示范项目',
        loadUrl: ctx => (ctx.authoring && ctx.authoring.demo_url) || null,
        writeUrl: ctx => (ctx.authoring && ctx.authoring.demo_write_url) || null,
        canWrite: ctx => Boolean(ctx.authoring && ctx.authoring.can_write_demo),
        exists: ctx => Boolean(ctx.authoring && ctx.authoring.has_demo)
    }
};

/** URL 上的 `authoring_target`。非法值按 `starter` 处理——录制入口不该因为拼错参数而打不开。 */
export function resolveAuthoringTarget (raw) {
    return AUTHORING_TARGETS[raw] || AUTHORING_TARGETS.starter;
}

/**
 * 保存成功后，把后端响应回灌进 ctx 的哪些字段。
 *
 * 这一步别省：ctx 里的地址是进入预览时的快照，首次保存前为 null（"重新载入"按钮
 * 一直点不动），覆盖保存后也仍指向旧状态。starter 上踩过一次，demo 会原样复现。
 */
export function mergeSavedProject (target, prev, saved) {
    if (!prev) return prev;
    if (target.key === 'demo') {
        return {
            ...prev,
            authoring: {
                ...prev.authoring,
                has_demo: saved.has_demo != null ? saved.has_demo : true,
                demo_url: saved.demo_url != null
                    ? saved.demo_url
                    : (prev.authoring && prev.authoring.demo_url) || null
            }
        };
    }
    return {
        ...prev,
        challenge: {
            ...prev.challenge,
            has_starter: saved.has_starter != null ? saved.has_starter : true,
            starter_url: saved.starter_url != null
                ? saved.starter_url
                : prev.challenge.starter_url
        }
    };
}
