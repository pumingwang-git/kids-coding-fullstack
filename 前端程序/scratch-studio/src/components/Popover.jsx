import React from 'react';
import {createPortal} from 'react-dom';
import {popoverStyle} from '../theme';

/**
 * 任务要求 / 提交记录 / 判定反馈的浮层。
 *
 * 必须 portal 到 body：合并之后触发按钮长在 Scratch 原生菜单栏**内部**，而那条栏
 * 有自己的层叠上下文与 overflow 收口，浮层留在原地随时可能被裁掉或压在下面。
 * 挂到 body 上，位置只由 `position: fixed` 决定，与 GUI 的内部结构彻底解耦。
 */
export default function Popover ({children, onClose, label}) {
    return createPortal(
        <div
            style={popoverStyle}
            role="dialog"
            aria-label={label || '详情'}
        >
            {onClose && (
                <button
                    style={{
                        float: 'right',
                        border: 'none',
                        background: 'transparent',
                        color: 'var(--muted)',
                        cursor: 'pointer',
                        fontSize: '14px',
                        lineHeight: 1,
                        padding: '2px 4px'
                    }}
                    aria-label="关闭"
                    onClick={onClose}
                >
                    ✕
                </button>
            )}
            {children}
        </div>,
        document.body
    );
}
