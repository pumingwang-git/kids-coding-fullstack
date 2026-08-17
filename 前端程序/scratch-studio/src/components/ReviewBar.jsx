import React from 'react';
import {barStyle, titleStyle, pillStyle, noteStyle} from '../theme';

/**
 * 教师批改台只读查看提交快照时的顶栏（`?mode=admin_review`）。
 *
 * 与 DemoBar 同一原则：本组件里一个写按钮都没有，"把学生交上来的版本改掉"这件事在
 * 结构上做不到。真正的边界在后端——`/api/admin/scratch/submissions/{id}` 只读，
 * 快照 `.sb3` 与 `project.json` 也只 GET。这里做的是移除入口。
 *
 * 标题带上学生与挑战，让老师在批改时一眼知道"这是谁、哪一关、第几次交"。
 */
export default function ReviewBar ({ctx}) {
    const snapshot = ctx.snapshot || {};
    const title = [
        ctx.student_name || `学生 #${ctx.student_id || ''}`,
        ctx.challenge_title || `挑战 #${ctx.challenge_id || ''}`,
        snapshot.revision_no != null ? `第 ${snapshot.revision_no} 版` : ''
    ].filter(Boolean).join(' · ');
    return (
        <div style={barStyle('admin')}>
            <span style={titleStyle}>提交快照 · {title}</span>
            <span style={pillStyle('accent')}>提交时冻结（只读）</span>
            <span style={noteStyle()}>这是学生交上来那一版，改动不会被保存。</span>
        </div>
    );
}
