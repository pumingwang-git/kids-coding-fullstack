import React, {useCallback, useEffect, useState} from 'react';
import {createWork, saveWorkSb3, updateWork} from '../api';
import {SAVE_SOURCE} from '../api/types';
import {grabStageSnapshot} from '../gui/stageSnapshot';
import {pillStyle, primaryBtnStyle, disabledStyle, noteStyle} from '../theme';
import {pushToast} from './Toast';
import MoreMenu from './MoreMenu';

/**
 * 自由作品的栏内内容（`?mode=free`）。
 *
 * 与闯关的 SaveSubmitBar 分开：那条有「提交作品」和判定徽标，自由作品没有提交
 * 一说——它只有保存，保存即创作本身。两个组件各管各的，就不会出现"自由作品上
 * 多了个提交按钮，点下去不知道在交什么"。
 *
 * 2026-08-19 合并进原生菜单栏后的三处变化：
 *  - 标题输入框删掉了。标题走官方的 `ProjectTitleInput`（`canEditTitle`），
 *    由 StudioApp 用 `projectTitle` / `onUpdateProjectTitle` 双向绑定后传进来，
 *    保存时取的就是它。工作台里只留一个改名入口。
 *  - 保存结果不再挂在栏里，改走 toast——栏高被 48px 钉死，消息一多就会折行。
 *  - 「返回我的作品」收进「更多」。
 *
 * 保存失败不丢 VM 编辑状态（与闯关同一约定），只提示可重试。
 */
export default function FreeBar ({ctx, vm, title, onProjectSaved}) {
    const [workId, setWorkId] = useState(ctx.id || null);
    const [isPublic, setIsPublic] = useState(ctx.is_public !== false);
    const [saveState, setSaveState] = useState('idle'); // idle | saving | saved | error
    const [savedOnce, setSavedOnce] = useState(Boolean(ctx.has_content));

    const handleSave = useCallback(async () => {
        if (!vm) {
            pushToast('尚未获得作品，无法保存', 'error');
            return;
        }
        setSaveState('saving');
        try {
            const blob = await vm.saveProjectSb3();
            // 顺序不能反：先打包再截图，两者之间学生没有操作机会，图与内容对得上。
            // 抓不到返回 null，这次保存就不带封面（服务端沿用旧的），不打断保存。
            const cover = await grabStageSnapshot(vm);
            const normalizedTitle = (title || '').trim() || '未命名作品';
            // 草稿首次保存时才建档，标题和公开状态在同一次操作中写入。
            const created = workId ? null : await createWork(normalizedTitle, isPublic);
            const savedId = workId || created.id;
            if (!workId) {
                setWorkId(savedId);
                const url = new URL(window.location.href);
                url.searchParams.set('work_id', String(savedId));
                url.searchParams.delete('draft');
                window.history.replaceState({}, '', url);
            }
            const res = await saveWorkSb3(savedId, blob, SAVE_SOURCE.MANUAL, cover);
            await updateWork(savedId, {title: normalizedTitle, is_public: isPublic});
            if (onProjectSaved) onProjectSaved();
            setSaveState('saved');
            setSavedOnce(true);
            pushToast(res.unchanged ? '内容未变，已同步' : '已保存', 'ok');
        } catch (e) {
            setSaveState('error');
            pushToast(`保存失败：${e.message}（可重试，编辑内容未丢失）`, 'error');
        }
    }, [vm, workId, title, isPublic, onProjectSaved]);

    // 保存是本能动作，给它一个本能快捷键。浏览器默认的"保存网页"没有意义，拦掉。
    useEffect(() => {
        const onKey = e => {
            if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
                // The official title field buffers edits until blur/Enter. Let
                // that field flush naturally instead of saving Redux's old title.
                const target = e.target;
                if (target && (target.tagName === 'INPUT'
                    || target.tagName === 'TEXTAREA'
                    || target.isContentEditable)) return;
                e.preventDefault();
                handleSave();
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [handleSave]);

    const saving = saveState === 'saving';

    return (
        <>
            <button
                style={{...pillStyle(isPublic ? 'accent' : 'neutral'), border: 'none', cursor: 'pointer'}}
                onClick={() => setIsPublic(v => !v)}
                title={isPublic
                    ? '保存后展出到作品广场，同学们能看到'
                    : '只有你自己能看到，不在广场展出'}
            >
                {isPublic ? '公开 · 展出中' : '私密'}
            </button>

            {savedOnce && saveState !== 'error' && (
                <span style={noteStyle()}>{saving ? '保存中…' : '已保存'}</span>
            )}

            <button
                style={{...primaryBtnStyle, ...(saving ? disabledStyle : {})}}
                onClick={handleSave}
                disabled={saving}
                title="保存作品（Ctrl/⌘ + S）"
            >
                {saving ? '保存中…' : '保存作品'}
            </button>

            <MoreMenu
                items={[
                    {
                        key: 'back',
                        label: '返回我的作品',
                        onSelect: () => {
                            window.location.href = '/areas/kids/explore/projects';
                        }
                    }
                ]}
            />
        </>
    );
}
