import React, {useCallback, useEffect, useState} from 'react';
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
    const galleryPreview = mode === 'preview';
    // 非法 / 缺省的 authoring_target 按 starter 处理：录制入口不该因为拼错参数打不开。
    const target = resolveAuthoringTarget(params.get('authoring_target'));

    // 保存成功后，用后端返回的 _serialize 结果刷新 ctx 里对应 target 的地址。
    // AuthoringBar 的「重新载入」读的就是那个地址，若保存后不同步，首次保存
    // （地址原为 null）按钮一直点不动，覆盖保存则仍指向旧快照。
    const handleProjectSaved = useCallback((saved) => {
        setCtx(prev => mergeSavedProject(target, prev, saved));
    }, [target]);

    // 必须在 GUI 的 ProjectFetcher 已挂载后再发起加载。默认项目 id=0 已内置在
    // scratch-gui 的 LegacyStorage 中，不需要联网；它会建立舞台和默认角色，保证
    // 添加角色、变量、上传素材等完整编辑能力可用。
    useEffect(() => {
        store.dispatch(setProjectId(defaultProjectId));
    }, [store]);

    useEffect(() => {
        const missing = adminReview ? !submissionId
            : adminPreview ? !challengeId
                : (freeEdit || galleryPreview) ? !workId
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
                } else if (freeEdit) {
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
                if (!cancelled) setStatus('ready');
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
    }, [adminPreview, adminReview, studentDemo, freeEdit, galleryPreview,
        blockId, challengeId, submissionId, workId, target, vm, store]);

    const loadingText = studentDemo ? '正在加载教师示范项目…'
        : adminReview ? '正在加载提交快照…'
            : freeEdit ? '正在加载我的作品…'
                : galleryPreview ? '正在加载作品预览…'
                    : '正在加载挑战与初始项目…';
    const backHref = freeEdit ? '/areas/kids/explore/projects'
        : galleryPreview ? '/areas/kids/explore'
            : lessonId && blockId ? `/learn/${lessonId}?block=${blockId}` : null;

    const bar = () => {
        if (!ctx) return null;
        if (adminReview) {
            return <ReviewBar ctx={ctx} />;
        }
        if (adminPreview) {
            return (
                <AuthoringBar
                    ctx={ctx}
                    vm={vm}
                    target={target}
                    onProjectSaved={handleProjectSaved}
                />
            );
        }
        // 无权查看时连只读栏也不渲染：那一屏只该有一句为什么看不到。
        if (studentDemo) {
            return status === 'locked' ? null : <DemoBar ctx={ctx} backHref={backHref} />;
        }
        if (freeEdit) {
            return <FreeBar ctx={ctx} vm={vm} />;
        }
        if (galleryPreview) {
            return <PreviewBar ctx={ctx} backHref={backHref} />;
        }
        return <SaveSubmitBar ctx={ctx} vm={vm} />;
    };

    return (
        <div style={{display: 'flex', flexDirection: 'column', height: '100%'}}>
            {bar()}
            <div style={{flex: 1, minHeight: 0, position: 'relative'}}>
                {/* canManageFiles=false 关掉整个「文件」菜单——里面的「保存到你的电脑」
                    不受 canSave 控制，留着就等于给学生一个一键下载答案的按钮。
                    这是移除入口，不是防篡改：真正的边界在后端的提交闸。 */}
                <GUI
                    canSave={false}
                    canEditTitle={false}
                    // 自由作品是学生自己的创作，允许下载/上传文件；闯关（防下载答案）
                    // 与只读模式（student_demo / preview / adminReview）一律关掉。
                    canManageFiles={freeEdit || !(studentDemo || galleryPreview || adminReview)}
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
