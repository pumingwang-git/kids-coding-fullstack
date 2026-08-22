import React, {useState, useCallback, useEffect} from 'react';
import {
    saveProjectSb3, submitProject, fetchSubmissions
} from '../api';
import {SAVE_SOURCE} from '../api/types';
import {
    titleStyle, pillStyle, btnStyle, primaryBtnStyle, disabledStyle,
    noteStyle, popoverNoteStyle
} from '../theme';
import {pushToast} from './Toast';
import MoreMenu from './MoreMenu';
import Popover from './Popover';
import {
    SUBMISSION_STATUS_TEXT, submitActionFor, canViewTeacherDemo
} from './challengeActions';

/**
 * 闯关的栏内内容（`?block_id=N`）。
 *
 * - 保存：vm.saveProjectSb3() → PUT /projects/{id}；失败不丢 VM 编辑状态，可重试。
 * - 提交：POST /submit，通过与否一律展示服务端返回的 submission_status，客户端不写"通过"。
 * - 「任务要求」：后端按规则原文生成的 checklist（中文、不含期望值）+ 提示。
 *   课时卡片只塞得下 80 字摘要，学生进了 Studio 就靠这个面板知道要做什么。
 * - 提交反馈：服务端在 submit 响应里给了逐条 feedback（label + 怎么改），
 *   只显示一个总分徽章等于把最有用的部分扔了。
 *
 * 2026-08-21 作业顶栏规则：
 *  - 只留两个按钮在明面上：「保存」（朴素）+「提交作品」（唯一的实心主按钮）。
 *    已通过后降级为朴素「再提交」；任务要求 / 提交记录 / 示范项目 / 返回课时收进「更多」。
 *  - 作业不允许分享到广场。自由作品的公开/私密和分享仅由 FreeBar 管理，避免题解
 *    在学生通过前后被公开给全班。
 *  - 三条消息位（保存 / 提交 / 分享）全部改走 toast。旧版把它们挂在栏里，
 *    `flexWrap: 'wrap'` 一折行就多出一整条杠。
 *  - 「项目 #N」删掉：学生看不懂，排查看地址栏就有。
 */
export default function SaveSubmitBar ({ctx, vm, backHref, demoHref, onSubmitted}) {
    const {block, challenge, project} = ctx;
    const blockId = block.id;
    const projectId = project && project.id;

    const [saveState, setSaveState] = useState('idle'); // idle | saving | saved | error
    const [submitState, setSubmitState] = useState('idle'); // idle | submitting | done | error
    const [lastSubmit, setLastSubmit] = useState(ctx.last_submission || null);
    const [submissions, setSubmissions] = useState([]);
    const [panel, setPanel] = useState(null); // null | 'task' | 'history' | 'feedback'
    const hasSavedRevision = Boolean(project && project.current_revision_no > 0) || saveState === 'saved';

    const checklist = Array.isArray(challenge.checklist) ? challenge.checklist : [];
    const hints = Array.isArray(challenge.hints) ? challenge.hints : [];
    // 提交响应的 feedback 与学生端 submissions 列表里的 feedback 同构：{note, items[]}
    const feedbackItems = (lastSubmit && lastSubmit.feedback && lastSubmit.feedback.items) || [];

    const handleSave = useCallback(async () => {
        if (!vm || !projectId) {
            pushToast('尚未获得项目版本，无法保存', 'error');
            return;
        }
        setSaveState('saving');
        try {
            const blob = await vm.saveProjectSb3();
            const res = await saveProjectSb3(projectId, blob, SAVE_SOURCE.MANUAL, challenge.id);
            setSaveState('saved');
            pushToast(res.unchanged ? '内容未变，已同步' : `已保存（版本 ${res.revision.revision_no}）`, 'ok');
        } catch (e) {
            // 关键：保存失败不丢 VM 状态，仅提示，可重试
            setSaveState('error');
            pushToast(`保存失败：${e.message}（可重试，编辑内容未丢失）`, 'error');
        }
    }, [vm, projectId, challenge.id]);

    useEffect(() => {
        const onKey = e => {
            if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
                e.preventDefault();
                handleSave();
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [handleSave]);

    const handleSubmit = useCallback(async () => {
        setSubmitState('submitting');
        try {
            const res = await submitProject(blockId);
            setLastSubmit(res);
            setSubmitState('done');
            setPanel('feedback');
            // `demo.available` 属于详情上下文，不在提交响应中。提交终态后重取一次，
            // 学生不用退出工作台就能看到刚解锁的示范项目入口。
            if (onSubmitted) Promise.resolve(onSubmitted()).catch(() => {});
            // 刷新历史
            fetchSubmissions(blockId)
                .then(d => setSubmissions(d.submissions || []))
                .catch(() => {});
        } catch (e) {
            // **把服务端文案原样显示出来**。这里原先只置一个 error 状态，界面永远是
            // 一句"提交失败，请重试"——而后端对这条路径准备了八种不同的失败原因
            // （还没保存 / 课时没解锁 / 上一次还在处理 / 提交太频繁 / 作品文件丢了 …），
            // 每一种要学生做的事都不一样。吞掉文案的结果是：学生只会一遍遍点重试，
            // 而其中大半种情况重试一万次也不会成功。
            setSubmitState('error');
            pushToast(`提交失败：${e.message || '请重试'}`, 'error');
        }
    }, [blockId]);

    const badge = lastSubmit
        ? SUBMISSION_STATUS_TEXT[lastSubmit.submission_status] || lastSubmit.submission_status
        : '未提交';
    const submitAction = submitActionFor(lastSubmit, hasSavedRevision, submitState === 'submitting');
    const demoAvailable = canViewTeacherDemo(ctx.demo, demoHref);

    const openHistory = useCallback(() => {
        setPanel(p => (p === 'history' ? null : 'history'));
        // 历史原先只在提交成功后刷新——刷新页面再进来点「提交记录」永远是空的。
        // 改成首次展开时懒加载一次。
        if (submissions.length === 0) {
            fetchSubmissions(blockId)
                .then(d => setSubmissions(d.submissions || []))
                .catch(() => {});
        }
    }, [blockId, submissions.length]);

    return (
        <>
            <span style={titleStyle} title={challenge.title}>{challenge.title}</span>
            <span style={pillStyle(lastSubmit ? 'accent' : 'neutral')}>判定：{badge}</span>

            {saveState === 'saved' && <span style={noteStyle()}>已保存</span>}

            <button
                style={{...btnStyle, ...(saveState === 'saving' || !projectId ? disabledStyle : {})}}
                onClick={handleSave}
                disabled={saveState === 'saving' || !projectId}
                title="保存作品（Ctrl/⌘ + S）"
            >
                {saveState === 'saving' ? '保存中…' : '保存'}
            </button>

            <button
                style={{
                    ...(submitAction.primary ? primaryBtnStyle : btnStyle),
                    ...(submitAction.disabled ? disabledStyle : {})
                }}
                onClick={handleSubmit}
                disabled={submitAction.disabled}
                title={submitAction.title}
            >
                {submitAction.label}
            </button>

            <MoreMenu
                items={[
                    {key: 'task', label: '任务要求', onSelect: () => setPanel(p => (p === 'task' ? null : 'task'))},
                    lastSubmit && {key: 'history', label: '提交记录', onSelect: openHistory},
                    lastSubmit && {
                        key: 'feedback',
                        label: '本次判定详情',
                        onSelect: () => setPanel(p => (p === 'feedback' ? null : 'feedback'))
                    },
                    demoAvailable && {
                        key: 'demo',
                        label: '查看教师示范',
                        onSelect: () => {
                            window.location.href = demoHref;
                        }
                    },
                    backHref && {
                        key: 'back',
                        label: '返回课时',
                        onSelect: () => {
                            window.location.href = backHref;
                        }
                    }
                ]}
            />

            {panel === 'task' && (
                <Popover label="任务要求" onClose={() => setPanel(null)}>
                    {challenge.instructions_md && (
                        <div style={{marginBottom: '8px', fontSize: '12px', whiteSpace: 'pre-line'}}>
                            {challenge.instructions_md}
                        </div>
                    )}
                    {checklist.length > 0 && (
                        <ol style={{margin: '0 0 8px', paddingLeft: '18px', fontSize: '12px'}}>
                            {checklist.map((item, i) => <li key={i}>{item}</li>)}
                        </ol>
                    )}
                    {hints.length > 0 && (
                        <div style={{fontSize: '12px'}}>
                            <b>提示</b>
                            <ul style={{margin: '4px 0 0', paddingLeft: '18px'}}>
                                {hints.map((hint, i) => <li key={i}>{hint}</li>)}
                            </ul>
                        </div>
                    )}
                    {!challenge.instructions_md && !checklist.length && !hints.length && (
                        <div style={popoverNoteStyle()}>老师还没有填写任务说明。</div>
                    )}
                </Popover>
            )}

            {panel === 'feedback' && lastSubmit && (
                <Popover label="判定详情" onClose={() => setPanel(null)}>
                    {/* 逐条判定反馈：哪条要求没过、怎么改。passed 时也展示——全部打勾
                        对学生是正向确认，不是废话。 */}
                    <div style={{fontSize: '12px', marginBottom: '6px'}}>
                        <b>{SUBMISSION_STATUS_TEXT[lastSubmit.submission_status] || lastSubmit.submission_status}</b>
                        {lastSubmit.score != null ? ` · ${lastSubmit.score} 分` : ''}
                        {lastSubmit.feedback && lastSubmit.feedback.note ? ` · ${lastSubmit.feedback.note}` : ''}
                    </div>
                    {feedbackItems.map((item, i) => (
                        <div key={i} style={{fontSize: '12px', marginBottom: '4px'}}>
                            {item.passed ? '✅' : '⬜'} {item.label}
                            {!item.passed && item.message && (
                                <div style={popoverNoteStyle()}>{item.message}</div>
                            )}
                        </div>
                    ))}
                    {lastSubmit.teacher && lastSubmit.teacher.comment && (
                        <div style={{fontSize: '12px', marginTop: '6px'}}>
                            <b>老师评语：</b>{lastSubmit.teacher.comment}
                        </div>
                    )}
                </Popover>
            )}

            {panel === 'history' && (
                <Popover label="提交记录" onClose={() => setPanel(null)}>
                    {submissions.length === 0 ? (
                        <div style={popoverNoteStyle()}>暂无提交记录</div>
                    ) : submissions.map(s => (
                        <div key={s.submission_id} style={{marginBottom: '8px', fontSize: '12px'}}>
                            <b>第 {s.attempt_no} 次</b> · {SUBMISSION_STATUS_TEXT[s.status] || s.status}
                            {s.score != null ? ` · ${s.score} 分` : ''}
                            <div style={popoverNoteStyle()}>{s.submitted_at}</div>
                            {s.review_comment && (
                                <div style={popoverNoteStyle()}>老师评语：{s.review_comment}</div>
                            )}
                        </div>
                    ))}
                </Popover>
            )}
        </>
    );
}
