import React from 'react';
import {titleStyle, pillStyle, btnStyle, noteStyle} from '../theme';

/**
 * 公开作品只读预览的栏内内容（`?mode=preview&work_id=N`）。
 *
 * 与 student_demo 的 DemoBar 同构：这里一个写按钮都没有，"看别人作品时不小心
 * 把改动存进自己作品"在结构上不成立。真正的边界在后端——画廊接口只认
 * `is_public`，私密作品一个字节都不发；这里只负责移除入口。
 */
export default function PreviewBar ({ctx, backHref}) {
    const author = ctx.author ? ctx.author.username : '同学';
    const title = ctx.title || '未命名作品';
    return (
        <>
            <span style={titleStyle} title={title}>{title}</span>
            <span style={pillStyle('accent')}>作品预览 · 只读</span>
            <span style={noteStyle()}>作者：{author} · 改动不会被保存</span>
            {backHref && (
                <a style={{...btnStyle, textDecoration: 'none'}} href={backHref}>
                    返回探索
                </a>
            )}
        </>
    );
}
