import React, {useCallback, useState} from 'react';
import {saveWorkSb3} from '../api';
import {SAVE_SOURCE} from '../api/types';
import {barStyle, titleStyle, pillStyle, btnStyle, primaryBtnStyle, disabledStyle, noteStyle} from '../theme';

/**
 * 自由作品编辑栏（`?mode=free&work_id=N`）。
 *
 * 与闯关的 SaveSubmitBar 分开：那条栏有「提交作品」和判定徽标，自由作品没有
 * 提交一说——它只有「保存」，保存即创作本身。两个组件各管各的，就不会出现
 * "自由作品上多了个提交按钮，点下去不知道在交什么"。
 *
 * 保存失败不丢 VM 编辑状态（与闯关同一约定），只提示可重试。
 */
export default function FreeBar ({ctx, vm}) {
    const workId = ctx.id;
    const [saveState, setSaveState] = useState('idle'); // idle | saving | saved | error
    const [saveMsg, setSaveMsg] = useState('');

    const handleSave = useCallback(async () => {
        if (!vm || !workId) {
            setSaveState('error');
            setSaveMsg('尚未获得作品，无法保存');
            return;
        }
        setSaveState('saving');
        setSaveMsg('');
        try {
            const blob = await vm.saveProjectSb3();
            const res = await saveWorkSb3(workId, blob, SAVE_SOURCE.MANUAL);
            setSaveState('saved');
            setSaveMsg(res.unchanged ? '内容未变，已同步' : '已保存');
        } catch (e) {
            setSaveState('error');
            setSaveMsg(`保存失败：${e.message}（可重试，编辑内容未丢失）`);
        }
    }, [vm, workId]);

    return (
        <div style={barStyle('student')}>
            <span style={titleStyle}>{ctx.title || '未命名作品'}</span>
            <span style={pillStyle('accent')}>{ctx.is_public ? '公开 · 展出中' : '私密'}</span>
            <span style={noteStyle()}>
                {ctx.has_content ? '自由创作作品' : '尚未保存过，改动请记得点保存'}
            </span>
            <button
                style={{...primaryBtnStyle, ...(saveState === 'saving' || !workId ? disabledStyle : {})}}
                onClick={handleSave}
                disabled={saveState === 'saving' || !workId}
            >
                {saveState === 'saving' ? '保存中…' : '保存作品'}
            </button>
            {saveMsg && (
                <span style={noteStyle(saveState === 'error' ? 'error' : 'ok')}>{saveMsg}</span>
            )}
            <a style={{...btnStyle, textDecoration: 'none'}} href="/areas/kids/explore/projects">
                返回我的作品
            </a>
        </div>
    );
}
