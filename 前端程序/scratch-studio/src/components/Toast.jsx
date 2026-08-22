import React, {useEffect, useState} from 'react';
import {createPortal} from 'react-dom';

/**
 * 操作结果浮层。
 *
 * 为什么要有它：合并进原生菜单栏之后，栏高被 48px 钉死。旧版把"保存失败""提交
 * 失败""分享成功"三条消息直接挂在栏里，`flexWrap: 'wrap'` 一折行就多出一整条杠
 * ——"两条杠"变三条的真凶就是它。消息挪到浮层，栏高才恒定。
 *
 * 成功类自动消失，失败类**不自动消失**：保存失败要学生看见并重试，四秒后自己
 * 溜走等于没提示过。失败项给一个显式的关闭按钮。
 */

let items = [];
let seq = 0;
const listeners = new Set();

function emit () {
    for (const fn of listeners) fn(items);
}

/**
 * @param {string} text 文案
 * @param {'ok'|'error'} tone 语气。error 不自动消失
 * @param {number} [ttl] 毫秒；error 默认 0（不消失）
 * @returns {number} id，可用于 dismissToast
 */
export function pushToast (text, tone = 'ok', ttl) {
    const id = ++seq;
    const life = ttl === undefined ? (tone === 'error' ? 0 : 4000) : ttl;
    items = [...items, {id, text, tone}];
    emit();
    if (life > 0) setTimeout(() => dismissToast(id), life);
    return id;
}

export function dismissToast (id) {
    items = items.filter(item => item.id !== id);
    emit();
}

const hostStyle = {
    position: 'fixed',
    top: '56px',
    right: '16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    zIndex: 2147483646,
    pointerEvents: 'none'
};

function toastStyle (tone) {
    return {
        pointerEvents: 'auto',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '10px',
        maxWidth: 'min(420px, calc(100vw - 32px))',
        padding: '10px 12px',
        borderRadius: '8px',
        border: `1px solid ${tone === 'error' ? 'var(--danger)' : 'var(--line)'}`,
        background: 'var(--paper)',
        color: tone === 'error' ? 'var(--danger)' : 'var(--ink)',
        fontFamily: 'var(--font-ui)',
        fontSize: '13px',
        lineHeight: 1.5,
        boxShadow: '0 4px 16px rgba(34, 43, 40, 0.18)'
    };
}

const closeStyle = {
    border: 'none',
    background: 'transparent',
    color: 'inherit',
    cursor: 'pointer',
    fontSize: '14px',
    lineHeight: 1,
    padding: '2px 4px'
};

/** 全局只挂一次（StudioApp 顶层）。 */
export default function ToastHost () {
    const [list, setList] = useState(items);
    useEffect(() => {
        listeners.add(setList);
        return () => listeners.delete(setList);
    }, []);
    if (list.length === 0) return null;
    return createPortal(
        <div style={hostStyle}>
            {list.map(item => (
                <div key={item.id} style={toastStyle(item.tone)} role="status">
                    <span style={{flex: 1}}>{item.text}</span>
                    <button
                        style={closeStyle}
                        aria-label="关闭提示"
                        onClick={() => dismissToast(item.id)}
                    >
                        ✕
                    </button>
                </div>
            ))}
        </div>,
        document.body
    );
}
