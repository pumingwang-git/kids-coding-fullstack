import React from 'react';
import {barStyle, titleStyle, pillStyle, btnStyle, noteStyle} from '../theme';

/**
 * 学生只读查看教师示范项目时的顶栏（`?mode=student_demo`）。
 *
 * 第三个组件而不是给 SaveSubmitBar 加一个 readonly 开关：那条栏里有保存和提交两个
 * 写按钮，加开关就意味着"某个分支下它们恰好没渲染"，而这里要的是**结构上不存在**。
 * 本组件里一个写按钮都没有，所以"看示范项目时误把答案存成自己的作品"这件事做不到。
 *
 * 只读同样不是靠本组件实现的。真正的边界在后端：提交拿到结果之前，
 * `GET /api/scratch/lesson-blocks/{id}/demo.sb3` 一个字节都不发。这里做的是移除入口，
 * 让学生不会误操作，也不会以为这份东西是自己的作品（见 21g 交接文档 §11）。
 */
export default function DemoBar ({ctx, backHref}) {
    const title = (ctx.challenge && ctx.challenge.title) || '教师示范项目';
    return (
        <div style={barStyle('admin')}>
            <span style={titleStyle}>{title}</span>

            <span style={pillStyle('accent')}>教师示范项目（只读）</span>
            <span style={noteStyle()}>可以点绿旗运行、翻看代码与角色，改动不会被保存。</span>

            {backHref && (
                <a style={{...btnStyle, textDecoration: 'none'}} href={backHref}>
                    返回课时
                </a>
            )}
        </div>
    );
}
