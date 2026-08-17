import React, {useState, useCallback} from 'react';
import {
    saveProjectSb3, submitProject,
    fetchSubmissions, shareWork
} from '../api';
import {SAVE_SOURCE} from '../api/types';

// 样式统一走 theme.js（平台令牌）：课程操作栏与教研操作栏是同一条横条的两种形态，
// 各写各的必然长出两套间距和两种按钮色。Scratch GUI 的紫色只属于它自己那一层。
import {
    barStyle, titleStyle, pillStyle,
    btnStyle, primaryBtnStyle, ghostBtnStyle, disabledStyle, noteStyle, popoverStyle
} from '../theme';

const STATUS_TEXT = {
    passed: '已通过',
    failed: '未通过',
    needs_review: '待人工点评',
    returned: '已退回重做'
};

/**
 * 保存 / 提交状态栏。
 * - 保存：vm.saveProjectSb3() → PUT /projects/{id}；失败不丢 VM 编辑状态，可重试。
 * - 提交：POST /submit，通过与否一律展示服务端返回的 submission_status，客户端不写"通过"。
 * - 「任务要求」：后端按规则原文生成的 checklist（中文、不含期望值）+ 提示。
 *   课时卡片只塞得下 80 字摘要，学生进了 Studio 就靠这个面板知道要做什么。
 * - 提交反馈：服务端在 submit 响应里给了逐条 feedback（label + 怎么改），
 *   只显示一个总分徽章等于把最有用的部分扔了。
 */
export default function SaveSubmitBar ({ctx, vm}) {
    const {block, challenge, project} = ctx;
    const blockId = block.id;
    const projectId = project && project.id;

    const [saveState, setSaveState] = useState('idle'); // idle | saving | saved | error
    const [saveMsg, setSaveMsg] = useState('');
    const [submitState, setSubmitState] = useState('idle'); // idle | submitting | done | error
    const [submitMsg, setSubmitMsg] = useState('');
    const [shareState, setShareState] = useState('idle'); // idle | sharing | done | error
    const [shareMsg, setShareMsg] = useState('');
    const [lastSubmit, setLastSubmit] = useState(ctx.last_submission || null);
    const [submissions, setSubmissions] = useState([]);
    const [showHistory, setShowHistory] = useState(false);
    const [showTask, setShowTask] = useState(false);
    const hasSavedRevision = Boolean(project && project.current_revision_no > 0) || saveState === 'saved';

    const checklist = Array.isArray(challenge.checklist) ? challenge.checklist : [];
    const hints = Array.isArray(challenge.hints) ? challenge.hints : [];
    // 提交响应的 feedback 与学生端 submissions 列表里的 feedback 同构：{note, items[]}
    const feedbackItems = (lastSubmit && lastSubmit.feedback && lastSubmit.feedback.items) || [];

    const handleSave = useCallback(async () => {
        if (!vm || !projectId) {
            setSaveState('error');
            setSaveMsg('尚未获得项目版本，无法保存');
            return;
        }
        setSaveState('saving');
        setSaveMsg('');
        try {
            const blob = await vm.saveProjectSb3();
            const res = await saveProjectSb3(projectId, blob, SAVE_SOURCE.MANUAL, challenge.id);
            setSaveState('saved');
            setSaveMsg(res.unchanged ? '内容未变，已同步' : `已保存（版本 ${res.revision.revision_no}）`);
        } catch (e) {
            // 关键：保存失败不丢 VM 状态，仅提示，可重试
            setSaveState('error');
            setSaveMsg(`保存失败：${e.message}（可重试，编辑内容未丢失）`);
        }
    }, [vm, projectId, challenge.id]);

    const handleSubmit = useCallback(async () => {
        setSubmitState('submitting');
        setSubmitMsg('');
        try {
            const res = await submitProject(blockId);
            setLastSubmit(res);
            setSubmitState('done');
            // 刷新历史
            fetchSubmissions(blockId)
                .then(d => setSubmissions(d.submissions || []))
                .catch(() => {});
        } catch (e) {
            // **把服务端文案原样显示出来**。这里原先只 setSubmitState('error')，
            // 界面永远是一句"提交失败，请重试"——而后端对这条路径准备了八种不同的
            // 失败原因（还没保存 / 课时没解锁 / 上一次还在处理 / 提交太频繁 /
            // 作品文件丢了 …），每一种要学生做的事都不一样。吞掉文案的结果是：
            // 学生只会一遍遍点重试，而其中大半种情况重试一万次也不会成功。
            //
            // 保存那条路（handleSave）本来就是这么做的，两条并排放着却不一致，
            // 说明当初是漏了，不是有意为之。
            setSubmitState('error');
            setSubmitMsg(e.message || '提交失败，请重试');
        }
    }, [blockId]);

    const badge = lastSubmit ? STATUS_TEXT[lastSubmit.submission_status] || lastSubmit.submission_status : '未提交';

    // 把闯关工作副本发布为一份独立的自由作品（广场快照）。幂等：已分享过时后端
    // 返回已有那条（already_shared=true），这里照常提示成功，不把 409 甩给学生。
    const handleShare = useCallback(async () => {
        if (!projectId || !hasSavedRevision) return;
        setShareState('sharing');
        setShareMsg('');
        try {
            const res = await shareWork(projectId);
            setShareState('done');
            setShareMsg(res.already_shared
                ? '这份作品已在广场展出（可在「我的作品」里管理）'
                : '已分享到广场！可以在「我的作品」里继续编辑或设为私密');
        } catch (e) {
            setShareState('error');
            setShareMsg(e.message || '分享失败，请重试');
        }
    }, [projectId, hasSavedRevision]);

    return (
        <div style={barStyle('student')}>
            <span style={titleStyle}>{challenge.title}</span>
            <span style={pillStyle(lastSubmit ? 'accent' : 'neutral')}>判定：{badge}</span>

            <span style={noteStyle()}>
                {projectId ? `项目 #${projectId}` : '新项目（提交前先保存）'}
            </span>

            <button
                style={{...btnStyle, ...(saveState === 'saving' || !projectId ? disabledStyle : {})}}
                onClick={handleSave}
                disabled={saveState === 'saving' || !projectId}
            >
                {saveState === 'saving' ? '保存中…' : '保存作品'}
            </button>

            <button
                style={{
                    ...primaryBtnStyle,
                    ...(submitState === 'submitting' || !hasSavedRevision ? disabledStyle : {})
                }}
                onClick={handleSubmit}
                disabled={submitState === 'submitting' || !hasSavedRevision}
                title={hasSavedRevision ? '' : '请先保存作品'}
            >
                {submitState === 'submitting' ? '提交中…' : '提交作品'}
            </button>

            <button
                style={{
                    ...btnStyle,
                    ...(shareState === 'sharing' || !hasSavedRevision ? disabledStyle : {})
                }}
                onClick={handleShare}
                disabled={shareState === 'sharing' || !hasSavedRevision}
                title={hasSavedRevision ? '把当前作品发布到作品广场，展出给同学看' : '请先保存作品'}
            >
                {shareState === 'sharing' ? '分享中…' : '分享到广场'}
            </button>

            {saveMsg && (
                <span style={noteStyle(saveState === 'error' ? 'error' : 'ok')}>{saveMsg}</span>
            )}
            {submitState === 'error' && (
                <span style={noteStyle('error')}>提交失败：{submitMsg}</span>
            )}
            {shareMsg && (
                <span style={noteStyle(shareState === 'error' ? 'error' : 'ok')}>{shareMsg}</span>
            )}

            <button style={ghostBtnStyle} onClick={() => setShowTask(s => !s)}>
                任务要求
            </button>
            <button
                style={ghostBtnStyle}
                onClick={() => {
                    // 历史原先只在提交成功后刷新——刷新页面再进来点「提交记录」永远是空的。
                    // 改成首次展开时懒加载一次。
                    setShowHistory(s => !s);
                    if (!showHistory && submissions.length === 0) {
                        fetchSubmissions(blockId)
                            .then(d => setSubmissions(d.submissions || []))
                            .catch(() => {});
                    }
                }}
            >
                提交记录
            </button>

            {showTask && (
                <div style={popoverStyle}>
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
                        <div style={noteStyle()}>老师还没有填写任务说明。</div>
                    )}
                </div>
            )}

            {submitState === 'done' && lastSubmit && (
                <div style={popoverStyle}>
                    {/* 逐条判定反馈：哪条要求没过、怎么改。passed 时也展示——全部打勾
                        对学生是正向确认，不是废话。 */}
                    <div style={{fontSize: '12px', marginBottom: '6px'}}>
                        <b>{STATUS_TEXT[lastSubmit.submission_status] || lastSubmit.submission_status}</b>
                        {lastSubmit.score != null ? ` · ${lastSubmit.score} 分` : ''}
                        {lastSubmit.feedback && lastSubmit.feedback.note ? ` · ${lastSubmit.feedback.note}` : ''}
                    </div>
                    {feedbackItems.map((item, i) => (
                        <div key={i} style={{fontSize: '12px', marginBottom: '4px'}}>
                            {item.passed ? '✅' : '⬜'} {item.label}
                            {!item.passed && item.message && (
                                <div style={noteStyle()}>{item.message}</div>
                            )}
                        </div>
                    ))}
                    {lastSubmit.teacher && lastSubmit.teacher.comment && (
                        <div style={{fontSize: '12px', marginTop: '6px'}}>
                            <b>老师评语：</b>{lastSubmit.teacher.comment}
                        </div>
                    )}
                </div>
            )}

            {showHistory && (
                <div style={popoverStyle}>
                    {submissions.length === 0 ? (
                        <div style={noteStyle()}>暂无提交记录</div>
                    ) : submissions.map(s => (
                        <div key={s.submission_id} style={{marginBottom: '8px', fontSize: '12px'}}>
                            <b>第 {s.attempt_no} 次</b> · {STATUS_TEXT[s.status] || s.status}
                            {s.score != null ? ` · ${s.score} 分` : ''}
                            <div style={noteStyle()}>{s.submitted_at}</div>
                            {s.review_comment && (
                                <div style={noteStyle()}>老师评语：{s.review_comment}</div>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
