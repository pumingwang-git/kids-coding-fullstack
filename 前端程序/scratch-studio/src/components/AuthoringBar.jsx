import React, {useState, useCallback} from 'react';
import {fetchChallengeSb3, uploadChallengeProject} from '../api';
import {
    barStyle, titleStyle, pillStyle,
    btnStyle, primaryBtnStyle, disabledStyle, noteStyle
} from '../theme';

/**
 * 教研的录制操作栏（`?mode=admin_preview`），按 `authoring_target` 服务两种目标：
 * 初始项目与示范项目。
 *
 * 与学生那条栏是两个组件而不是一个组件加 if：两边调的是完全不同的端点，混在一起
 * 迟早会有一次"教研点了保存，写进了某个学生的作品"。分开写，这类事故在结构上不成立。
 *
 * 初始项目与示范项目**共用本组件**却是另一码事：它们调的是同一套管理端端点，差别
 * 只有"哪个 URL"，而那个差别已经收口在 `authoringTargets.js` 的表里了。组件本身
 * 不知道 starter 和 demo 的区别——它只会照着 target 给的取值器办事。
 *
 * 四件事：
 *  1. 明确告诉老师这是预览视图，且**正在录制哪一份**（两个入口长得一样，靠文案区分
 *     不可靠，所以顶栏常驻一枚「正在录制：×××」徽标）；
 *  2. 把当前那一份重新装回编辑器（改坏了可以退回上一版）；
 *  3. 把眼下编辑器里的内容存成本关的这一份；
 *  4. 一个学生数据的写入口都不给。
 *
 * 能不能写由服务端下发的 `can_write_*` 决定，本组件不复述状态机——已发布的挑战那两个
 * 字段是 false / null，按钮自然点不动，文案直接用服务端的 `locked_reason`。
 */
export default function AuthoringBar ({ctx, vm, target, onReloadProject, onProjectSaved}) {
    const {challenge, authoring} = ctx;
    const writeUrl = target.writeUrl(ctx);
    const loadUrl = target.loadUrl(ctx);
    const canWrite = Boolean(target.canWrite(ctx) && writeUrl);

    const [state, setState] = useState('idle'); // idle | saving | saved | error
    const [message, setMessage] = useState('');
    const [reloading, setReloading] = useState(false);
    const exists = target.exists(ctx);

    const handleWrite = useCallback(async () => {
        setState('saving');
        setMessage('');
        try {
            const blob = await vm.saveProjectSb3();
            // 后端返回 _serialize(challenge)，含刷新后的地址与 has_* 标记。不能丢弃：
            // ctx 里的地址是进入预览时的快照，首次保存前为 null（按钮一直点不动），
            // 覆盖保存后也仍指向旧状态。回灌规则见 authoringTargets.mergeSavedProject。
            const saved = await uploadChallengeProject(writeUrl, blob, target.filename);
            if (onProjectSaved) onProjectSaved(saved);
            setState('saved');
            setMessage(target.savedNote);
        } catch (e) {
            // 与学生端保存同一条纪律：失败不动 VM，编辑内容不丢，可重试。
            setState('error');
            setMessage(`保存失败：${e.message}（编辑内容未丢失，可重试）`);
        }
    }, [vm, writeUrl, target, onProjectSaved]);

    const handleReload = useCallback(async () => {
        if (!loadUrl) return;
        setReloading(true);
        setMessage('');
        try {
            const buffer = await fetchChallengeSb3(loadUrl);
            await vm.loadProject(buffer);
            setState('idle');
            setMessage(target.reloadedNote);
            if (onReloadProject) onReloadProject();
        } catch (e) {
            setState('error');
            setMessage(`载入失败：${e.message}`);
        } finally {
            setReloading(false);
        }
    }, [vm, loadUrl, target, onReloadProject]);

    return (
        <div style={barStyle('admin')}>
            <span style={titleStyle}>{challenge.title}</span>

            <span style={pillStyle('accent')}>管理员预览</span>
            {/* 两个录制入口长得一样，这枚徽标是老师唯一能确认自己在录哪一份的地方。 */}
            <span style={pillStyle('accent')}>{target.recordingLabel}</span>
            <span style={pillStyle(challenge.status === 'published' ? 'warn' : 'neutral')}>
                {challenge.status === 'published' ? '已发布' : '草稿'} · 第 {challenge.version} 版
            </span>
            <span style={noteStyle()}>
                {target.label}：{exists ? '已上传' : '未上传'}
            </span>

            <button
                style={{...btnStyle, ...(loadUrl && !reloading ? {} : disabledStyle)}}
                onClick={handleReload}
                disabled={!loadUrl || reloading}
                title={loadUrl ? '放弃当前改动，装回服务器上的那一版' : target.emptyHint}
            >
                {reloading ? '载入中…' : '重新载入'}
            </button>

            <button
                style={{...primaryBtnStyle, ...(canWrite && state !== 'saving' ? {} : disabledStyle)}}
                onClick={handleWrite}
                disabled={!canWrite || state === 'saving'}
                title={canWrite
                    ? `立即上传编辑器当前内容，保存为本关${target.label}`
                    : (authoring && authoring.locked_reason) || ''}
            >
                {state === 'saving' ? '正在上传…' : `保存并上传${target.label}`}
            </button>

            {!canWrite && authoring && authoring.locked_reason && (
                <span style={noteStyle('muted')}>{authoring.locked_reason}</span>
            )}
            {message && (
                <span style={noteStyle(state === 'error' ? 'error' : 'ok')}>{message}</span>
            )}

            {/* 学生视图里这条位置是「保存作品/提交作品」。这里一个都不给：
                预览绝不产生学生作品或提交记录（21f 决策记录同款口径）。 */}
            <span style={noteStyle()}>预览不会产生学生作品或提交记录</span>
        </div>
    );
}
