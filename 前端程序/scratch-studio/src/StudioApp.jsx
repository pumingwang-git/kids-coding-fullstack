import React, {useCallback, useEffect, useRef, useState} from 'react';
import {useStore} from 'react-redux';
import GUI, {defaultProjectId, setProjectId} from '@scratch/scratch-gui';
import {
    fetchLessonBlockContext,
    fetchStarterSb3,
    fetchDemoSb3,
    fetchProjectContentSb3,
    fetchAdminStudioContext,
    fetchChallengeSb3,
    fetchAdminReviewContext,
    fetchSubmissionSb3,
    fetchWorkContext,
    fetchWorkContentSb3,
    fetchGalleryWork,
    fetchGalleryContentSb3
} from './api';
import {resolveAuthoringTarget, mergeSavedProject} from './authoringTargets';
import SaveSubmitBar from './components/SaveSubmitBar';
import AuthoringBar from './components/AuthoringBar';
import DemoBar from './components/DemoBar';
import ReviewBar from './components/ReviewBar';
import FreeBar from './components/FreeBar';
import PreviewBar from './components/PreviewBar';
import StudioBar from './components/StudioBar';
import ToastHost from './components/Toast';
import {applyBranding} from './gui/menuBarSlot';
import {capabilitiesFor} from './gui/studioCapabilities';
import {subscribeProjectTitle} from './gui/projectTitle';

/**
 * `setProjectTitle` 的 action type。
 *
 * scratch-gui 的包入口没有导出这个 action creator（`exported-reducers.ts` 里没有它），
 * 而 `reducers/project-title.js` 是包内路径——babel-loader 排除了 node_modules，
 * import 进来不会被编译。所以这里照抄常量自己发，比改整条构建划算。
 * 出处：`node_modules/@scratch/scratch-gui/src/reducers/project-title.js:1`
 */
const SET_PROJECT_TITLE = 'projectTitle/SET_PROJECT_TITLE';
const SET_PROJECT_CHANGED = 'scratch-gui/project-changed/SET_PROJECT_CHANGED';

/**
 * 工作台的标。主站资源，生产同源；Studio 直连 8602/8611 时会 404，那时保留官方标
 * （`swapLogo` 预载失败就不换，宁可还是官方标也不要一个裂图）。
 *
 * 图是扣掉底色的透明 PNG 转 webp：原图那层浅青底和字母的柔和投影都是照着浅底画的，
 * 压在深绿菜单栏上会变成一圈浅色毛边，所以底色和投影一起去掉了。高 128px 是给 2x 屏
 * 留的余量——菜单栏里实际只显示 1.6rem（≈25.6px），宽度按比例走。
 */
const PLATFORM_LOGO = '/assets/scratch-wordmark-128.webp';

/** 等待官方 GUI 完成默认项目加载（loadingState 进入 SHOWING_*） */
function waitUntilShown (store, timeout = 15000) {
    return new Promise((resolve, reject) => {
        const start = Date.now();
        const check = () => {
            const loadingState = store.getState().scratchGui.projectState.loadingState;
            if (loadingState === 'SHOWING_WITHOUT_ID' || loadingState === 'SHOWING_WITH_ID') {
                resolve();
                return;
            }
            if (Date.now() - start > timeout) {
                reject(new Error('编辑器初始化超时'));
                return;
            }
            setTimeout(check, 100);
        };
        check();
    });
}

const overlayStyle = {
    position: 'absolute',
    inset: 0,
    background: 'var(--paper)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '0 24px',
    textAlign: 'center',
    fontFamily: 'var(--font-ui)',
    fontSize: '15px',
    color: 'var(--muted)',
    zIndex: 100,
    gap: '16px'
};

/**
 * Studio 外壳：
 *  - 始终挂载 <GUI>（官方默认项目 + 绿旗，可立即运行）
 *  - 挂载后拉取上下文，覆盖加载 .sb3
 *  - 顶部操作栏按身份分三种形态
 *
 * ## 五种入口
 *
 * | URL | 身份 | 上下文来源 | 顶部栏 | 装载 |
 * | --- | --- | --- | --- | --- |
 * | `?block_id=N` | 学生 | `GET /api/scratch/lesson-blocks/{N}` | 保存 / 提交 | 我的作品，否则初始项目 |
 * | `?mode=admin_preview&challenge_id=N&authoring_target=starter\|demo` | 教研 | `GET /api/admin/scratch/challenges/{N}/studio-context` | 录制栏 | 该 target 的当前那一份 |
 * | `?mode=student_demo&block_id=N` | 已提交学生 | `GET /api/scratch/lesson-blocks/{N}` | 只读栏 | 教师示范项目 |
 * | `?mode=free&work_id=N` | 学生 | `GET /api/scratch/works/{N}` | 自由创作栏 | 我的自由作品 |
 * | `?mode=preview&work_id=N` | 学生 | `GET /api/scratch/gallery/{N}` | 只读预览栏 | 公开作品（画廊） |
 *
 * 教研这条**不能**复用学生那条：学生端要过课包发布、两道解锁闸、且挑战必须已发布
 * （草稿按 404）。教研要编的恰恰是草稿，而草稿通常还没绑到任何课时块上——
 * 从设计上就走不通，不是配一配能通的事（详见 21b 补充实施记录 2026-08-14）。
 *
 * `student_demo` 复用学生详情接口是有意的：需要的东西（标题、`demo.available`、
 * `demo.url`）那里全都有，不必另开一条上下文接口。但装载走**独立的第三条支路**，
 * 绝不落进下面 `hasContent ? 我的作品 : 初始项目` 的分支——那会把教师答案载入学生
 * 作品 VM，接着一次保存就把答案写进作品历史（21g 交接文档 §4.3 末尾警告的事故）。
 *
 * `free` / `preview` 与闯关的互斥同理：free 装的是学生自己的自由作品（可能被编辑
 * 保存回 `PUT /works/{id}`），preview 装的是**别人**的公开作品——两条装载支路
 * 分开写，就不会出现"预览别人作品时一次保存把它写进自己名下"的混账事。
 */
export default function StudioApp () {
    const store = useStore();
    const vm = store.getState().scratchGui.vm;
    const projectDirtyRef = useRef(false);

    const [ctx, setCtx] = useState(null);
    const [status, setStatus] = useState('loading'); // loading | ready | locked | error
    const [errorMsg, setErrorMsg] = useState('');

    const params = new URLSearchParams(window.location.search);
    const blockId = params.get('block_id');
    const lessonId = params.get('lesson_id');
    const challengeId = params.get('challenge_id');
    const submissionId = params.get('submission_id');
    const workId = params.get('work_id');
    const mode = params.get('mode');
    const adminPreview = mode === 'admin_preview';
    const adminReview = mode === 'admin_review';
    const studentDemo = mode === 'student_demo';
    const freeEdit = mode === 'free';
    const draftEdit = freeEdit && !workId && params.get('draft') === '1';
    const galleryPreview = mode === 'preview';
    // 非法 / 缺省的 authoring_target 按 starter 处理：录制入口不该因为拼错参数打不开。
    const target = resolveAuthoringTarget(params.get('authoring_target'));

    // 六种形态收敛成一个名字，能力查表（`gui/studioCapabilities.js`）。
    // 别在 JSX 里就地拼布尔表达式——上一版就是那么写的，写出了一条"注释说关掉、
    // 实际开着"的文件菜单，学生能把作业下载走。
    const studioMode = adminReview ? 'admin_review'
        : adminPreview ? 'admin_preview'
            : studentDemo ? 'student_demo'
                : freeEdit ? 'free'
                    : galleryPreview ? 'gallery_preview'
                        : 'challenge';
    const caps = capabilitiesFor(studioMode);

    // 作品标题走官方菜单栏里那个标题输入框（`canEditTitle`），我们自己的栏里不再放
    // 第二个输入框。redux 的 `projectTitle` 是唯一事实来源：进来时把上下文里的标题
    // 写进去，学生改完再读回来，保存时取的就是它。
    const [workTitle, setWorkTitle] = useState('未命名作品');

    useEffect(() => {
        if (!ctx) return;
        const title = ctx.title || (ctx.challenge && ctx.challenge.title) || '未命名作品';
        // 官方 TitledHOC 挂载时会先把标题设成默认值（"Scratch Project"）。我们的
        // 上下文是异步到的，落在它之后，所以这次覆盖有效。
        store.dispatch({type: SET_PROJECT_TITLE, title});
    }, [ctx, store]);

    useEffect(() => {
        return subscribeProjectTitle(store, next => {
            setWorkTitle(prev => (prev === next ? prev : next));
        });
    }, [store]);

    // 换标 + 注入菜单栏样式。放在这里而不是 index.jsx：它依赖菜单栏已经渲染出来，
    // 而菜单栏是 GUI 的一部分，与本组件同一次提交挂载。
    useEffect(() => {
        applyBranding({logoSrc: PLATFORM_LOGO, logoAlt: 'Scratch 工作台'});
    }, []);

    // 保存成功后，用后端返回的 _serialize 结果刷新 ctx 里对应 target 的地址。
    // AuthoringBar 的「重新载入」读的就是那个地址，若保存后不同步，首次保存
    // （地址原为 null）按钮一直点不动，覆盖保存则仍指向旧快照。
    const handleProjectSaved = useCallback((saved) => {
        setCtx(prev => mergeSavedProject(target, prev, saved));
        projectDirtyRef.current = false;
        store.dispatch({type: SET_PROJECT_CHANGED, changed: false});
    }, [target, store]);

    // Studio 走平台自己的保存接口，官方 ProjectSaverHOC 不会替我们清掉脏状态。
    // 关闭/刷新时直接读取 Redux，避免 React 闭包拿到过期的编辑状态。
    const markProjectSaved = useCallback(() => {
        projectDirtyRef.current = false;
        store.dispatch({type: SET_PROJECT_CHANGED, changed: false});
    }, [store]);

    useEffect(() => {
        const markProjectDirty = () => {
            projectDirtyRef.current = true;
        };
        vm.on('PROJECT_CHANGED', markProjectDirty);
        return () => vm.removeListener('PROJECT_CHANGED', markProjectDirty);
    }, [vm]);

    useEffect(() => {
        const warnBeforeUnload = event => {
            if (!projectDirtyRef.current) return;
            event.preventDefault();
            event.returnValue = true;
        };
        window.addEventListener('beforeunload', warnBeforeUnload);
        return () => window.removeEventListener('beforeunload', warnBeforeUnload);
    }, [store]);

    // 提交成功后只刷新作业元数据（判定、示范项目开放状态等），不重新加载 VM 项目，
    // 避免学生刚完成提交就被服务器版本覆盖当前编辑中的内容。
    const handleChallengeSubmitted = useCallback(async () => {
        if (!blockId) return;
        const fresh = await fetchLessonBlockContext(blockId);
        setCtx(fresh);
    }, [blockId]);

    // 必须在 GUI 的 ProjectFetcher 已挂载后再发起加载。默认项目 id=0 已内置在
    // scratch-gui 的 LegacyStorage 中，不需要联网；它会建立舞台和默认角色，保证
    // 添加角色、变量、上传素材等完整编辑能力可用。
    useEffect(() => {
        store.dispatch(setProjectId(defaultProjectId));
    }, [store]);

    useEffect(() => {
        const missing = adminReview ? !submissionId
            : adminPreview ? !challengeId
            : (freeEdit || galleryPreview) ? (!workId && !draftEdit)
                    : !blockId;
        if (missing) {
            setStatus('error');
            setErrorMsg(adminReview
                ? '缺少 submission_id 参数（请从批改台进入）'
                : adminPreview
                    ? '缺少 challenge_id 参数（请从管理端的挑战列表进入预览）'
                    : (freeEdit || galleryPreview)
                        ? '缺少 work_id 参数（请从我的作品或探索页进入）'
                        : '缺少 block_id 参数（请从课时进入工作台）');
            return;
        }
        let cancelled = false;
        (async () => {
            try {
                const data = adminReview
                    ? await fetchAdminReviewContext(submissionId)
                    : adminPreview
                        ? await fetchAdminStudioContext(challengeId)
                            : draftEdit
                                ? {id: null, title: '未命名作品', is_public: false, has_content: false}
                            : freeEdit
                            ? await fetchWorkContext(workId)
                            : galleryPreview
                                ? await fetchGalleryWork(workId)
                                : await fetchLessonBlockContext(blockId);
                if (cancelled) return;
                setCtx(data);

                // 开放判断只认后端下发的 available。**不用"有没有 url"代替**——将来
                // 后端若改成先发地址后校验，前端这一支就会静默变成"总是开放"。
                if (studentDemo && !(data.demo && data.demo.available)) {
                    setStatus('locked');
                    setErrorMsg((data.demo && data.demo.notice)
                        || '提交作品并得到本次结果后，才能查看教师示范项目。');
                    return;
                }

                // 等官方默认项目加载完，再覆盖为本次要看的那一份
                await waitUntilShown(store);

                if (adminReview) {
                    // 第四条互斥支路：只装「提交时冻结的那一版」快照，不碰学生当前副本，
                    // 也不碰挑战初始项目——老师看到的必须与判定证据是同一份。
                    const url = data.snapshot && data.snapshot.download_url;
                    if (url) {
                        const buf = await fetchSubmissionSb3(url);
                        if (!cancelled) await vm.loadProject(buf);
                    }
                } else if (studentDemo) {
                    // 第三条互斥支路：只装示范项目，不碰学生作品，也不碰初始项目。
                    const buf = await fetchDemoSb3(blockId);
                    if (!cancelled) await vm.loadProject(buf);
                } else if (freeEdit && !draftEdit) {
                    // 第五条互斥支路：装**自己的**自由作品，可编辑可保存回 PUT /works/{id}。
                    // 与 preview 共用 work_id 参数但上下文来源不同（/works/{id} 是本人视图），
                    // 且这条路径的保存目标只能是同一份作品——结构上不可能写进别人的作品。
                    if (data.content_url) {
                        const buf = await fetchWorkContentSb3(workId);
                        if (!cancelled) await vm.loadProject(buf);
                    }
                } else if (galleryPreview) {
                    // 第六条互斥支路：只装**公开**作品，只读，没有任何写按钮。
                    // 边界在后端（画廊只认 is_public），这里移除一切保存入口。
                    const buf = await fetchGalleryContentSb3(workId);
                    if (!cancelled) await vm.loadProject(buf);
                } else if (adminPreview) {
                    // 管理端预览没有 content（那是学生的作品），装的是本 target 的当前版本。
                    const url = target.loadUrl(data);
                    if (url) {
                        const buf = await fetchChallengeSb3(url);
                        if (!cancelled) await vm.loadProject(buf);
                    }
                } else {
                    const hasContent = Boolean(data.project && data.project.content_url);
                    if (hasContent) {
                        const buf = await fetchProjectContentSb3(data.project.id);
                        if (!cancelled) await vm.loadProject(buf);
                    } else if (data.challenge && data.challenge.starter_url) {
                        const buf = await fetchStarterSb3(blockId);
                        if (!cancelled) await vm.loadProject(buf);
                    }
                }
                if (!cancelled) {
                    // 装载 .sb3 也会触发 VM 的 PROJECT_CHANGED；它是服务器基线，不能
                    // 让学生什么都没改就收到离开提示。
                    projectDirtyRef.current = false;
                    setStatus('ready');
                }
            } catch (e) {
                if (!cancelled) {
                    setStatus('error');
                    setErrorMsg(e.message || String(e));
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [adminPreview, adminReview, studentDemo, freeEdit, draftEdit, galleryPreview,
        blockId, challengeId, submissionId, workId, target, vm, store]);

    const loadingText = studentDemo ? '正在加载教师示范项目…'
        : adminReview ? '正在加载提交快照…'
        : freeEdit ? (draftEdit ? '正在打开新的创作…' : '正在加载我的作品…')
                : galleryPreview ? '正在加载作品预览…'
                    : '正在加载挑战与初始项目…';
    const backHref = freeEdit ? '/areas/kids/explore/projects'
        : galleryPreview ? '/areas/kids/explore'
            : lessonId && blockId ? `/learn/${lessonId}?block=${blockId}` : null;
    const demoHref = lessonId && blockId
        ? `?lesson_id=${encodeURIComponent(lessonId)}&block_id=${encodeURIComponent(blockId)}&mode=student_demo`
        : null;

    /**
     * 六种形态的**栏内内容**（不再是六条独立横栏）。
     *
     * 内容统一交给 `StudioBar`：它把这些节点 portal 进 Scratch 原生菜单栏内部的槽位，
     * 页面上只剩一条 48px 的栏；拿不到槽位（GUI 版本换了结构）时退回独立横条。
     *
     * `tone` 决定身份色带：合并前"这不是学生视图"靠整条栏的薄荷底色，合并后底色没了，
     * 由色带 + 栏内常驻标签接手。教研与批改台都算后台视图。
     */
    const bar = () => {
        if (!ctx) return null;
        let tone = 'student';
        let content = null;
        if (adminReview) {
            tone = 'admin';
            content = <ReviewBar ctx={ctx} />;
        } else if (adminPreview) {
            tone = 'admin';
            content = (
                <AuthoringBar
                    ctx={ctx}
                    vm={vm}
                    target={target}
                    onProjectSaved={handleProjectSaved}
                />
            );
        } else if (studentDemo) {
            // 无权查看时连只读栏也不渲染：那一屏只该有一句为什么看不到。
            if (status === 'locked') return null;
            tone = 'readonly';
            content = <DemoBar ctx={ctx} backHref={backHref} />;
        } else if (freeEdit) {
            content = <FreeBar ctx={ctx} vm={vm} title={workTitle} onProjectSaved={markProjectSaved} />;
        } else if (galleryPreview) {
            tone = 'readonly';
            content = <PreviewBar ctx={ctx} backHref={backHref} />;
        } else {
            content = (
                <SaveSubmitBar
                    ctx={ctx}
                    vm={vm}
                    backHref={backHref}
                    demoHref={demoHref}
                    onSubmitted={handleChallengeSubmitted}
                    onProjectSaved={markProjectSaved}
                />
            );
        }
        return <StudioBar tone={tone} hideDebug={!caps.showDebug}>{content}</StudioBar>;
    };

    return (
        <div style={{display: 'flex', flexDirection: 'column', height: '100%'}}>
            {/* 操作结果浮层。栏高被 48px 钉死之后，消息没地方挂了，只能走浮层。 */}
            <ToastHost />
            {bar()}
            <div style={{flex: 1, minHeight: 0, position: 'relative'}}>
                {/* canManageFiles=false 关掉整个「文件」菜单——里面的「保存到你的电脑」
                    不受 canSave 控制，留着就等于给学生一个一键下载答案的按钮。
                    这是移除入口，不是防篡改：真正的边界在后端的提交闸。 */}
                <GUI
                    /* canSave 必须保持 false。打开它等于把保存交给官方
                       ProjectSaverHOC：它会先把脏素材 `scratchStorage.store()` 推给
                       Scratch 官方素材服务器，再调 `storage.saveProject`——我们的后端
                       一个字节都收不到，而学生会看到一串莫名其妙的保存失败。
                       平台的保存按钮长在菜单栏槽位里，走自己的 PUT。 */
                    canSave={false}
                    /* 同理不开 canShare：那条路会连带触发官方保存链路（menu-bar.jsx
                       handleClickShare），且文案不可控。公开/私密由 FreeBar 自己管。 */
                    canShare={false}
                    /* 标题是唯一交给官方组件的东西：ProjectTitleInput 只 dispatch
                       setProjectTitle，不碰任何保存链路（已核 project-title-input.jsx）。
                       只有自由创作能改名；作业/闯关的名字是老师定的，只读渲染。 */
                    canEditTitle={caps.canEditTitle}
                    /* 右上角账号区：本站没有 Scratch 会话，全部关掉，省得出现
                       "登录 / 我的东西"这类指向官方社区的入口。 */
                    accountMenuOptions={{
                        canHaveSession: false,
                        canRegister: false,
                        canLogin: false,
                        canLogout: false
                    }}
                    /* 文件菜单（新建 / 从电脑上传 / 保存到你的电脑）按形态查表。
                       ⚠️ 这里曾经写成
                           freeEdit || !(studentDemo || galleryPreview || adminReview)
                       注释说"闯关一律关掉"，可闯关那支真算出来是 true——作业模式下
                       学生一直能把作业导出、也能拿别人的 .sb3 顶上来交。表在
                       gui/studioCapabilities.js，有测试钉着。 */
                    canManageFiles={caps.canManageFiles}
                />
                {status !== 'ready' && (
                    <div style={overlayStyle}>
                        <div>
                            {status === 'loading' && loadingText}
                            {status === 'locked' && errorMsg}
                            {status === 'error' && `加载失败：${errorMsg}`}
                        </div>
                        {status === 'error' && (
                            <button
                                style={{
                                    padding: '8px 20px',
                                    borderRadius: '8px',
                                    border: '1px solid var(--line)',
                                    background: 'var(--paper)',
                                    color: 'var(--ink)',
                                    cursor: 'pointer',
                                    fontFamily: 'var(--font-ui)',
                                    fontSize: '14px',
                                    fontWeight: 600
                                }}
                                onClick={() => {
                                    if (window.history.length > 1) {
                                        window.history.back();
                                    } else {
                                        window.location.href = backHref || '/';
                                    }
                                }}
                            >
                                返回
                            </button>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
