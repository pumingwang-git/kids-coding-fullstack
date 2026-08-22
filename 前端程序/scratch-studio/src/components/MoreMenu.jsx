import React, {useCallback, useEffect, useRef, useState} from 'react';
import {ghostBtnStyle, disabledStyle} from '../theme';

/**
 * 栏内的「⋯ 更多」下拉。
 *
 * 排版纪律（见《49》§5.2）：整条栏只留一个实心主按钮 + 一个朴素「保存」，
 * 其余次级动作（任务要求、提交记录、分享到广场、重新载入、返回…）全收进这里。
 * 不这么收，闯关模式七八个按钮一字排开，合并进 48px 只会更挤。
 *
 * 菜单本身用 fixed 定位并挂在栏下方：Scratch GUI 内部有自己的层叠上下文，
 * absolute 会被裁切。
 */
export default function MoreMenu ({items, label = '更多'}) {
    const [open, setOpen] = useState(false);
    const [pos, setPos] = useState({top: 52, right: 16});
    const btnRef = useRef(null);
    const menuRef = useRef(null);

    const usable = (items || []).filter(Boolean);

    const place = useCallback(() => {
        const rect = btnRef.current && btnRef.current.getBoundingClientRect();
        if (!rect) return;
        // 纵向对齐整条栏的下沿，不是按钮的下沿：按钮只有 32px 高，按它算菜单会压住
        // 栏底那 4px（实测 top=44 而栏高 48）。找不到栏就退回按钮下沿。
        const bar = document.querySelector('header[class*="menu-bar_menu-bar"]');
        const anchorBottom = bar ? bar.getBoundingClientRect().bottom : rect.bottom;
        setPos({
            top: Math.round(anchorBottom + 4),
            right: Math.round(Math.max(8, window.innerWidth - rect.right))
        });
    }, []);

    useEffect(() => {
        if (!open) return undefined;
        place();
        const onDocDown = e => {
            if (menuRef.current && menuRef.current.contains(e.target)) return;
            if (btnRef.current && btnRef.current.contains(e.target)) return;
            setOpen(false);
        };
        const onKey = e => {
            if (e.key === 'Escape') setOpen(false);
        };
        document.addEventListener('mousedown', onDocDown);
        document.addEventListener('keydown', onKey);
        window.addEventListener('resize', place);
        return () => {
            document.removeEventListener('mousedown', onDocDown);
            document.removeEventListener('keydown', onKey);
            window.removeEventListener('resize', place);
        };
    }, [open, place]);

    if (usable.length === 0) return null;

    return (
        <>
            <button
                ref={btnRef}
                style={ghostBtnStyle}
                aria-haspopup="menu"
                aria-expanded={open}
                onClick={() => setOpen(v => !v)}
            >
                {label} ▾
            </button>
            {open && (
                <div
                    ref={menuRef}
                    role="menu"
                    style={{
                        position: 'fixed',
                        top: `${pos.top}px`,
                        right: `${pos.right}px`,
                        minWidth: '180px',
                        background: 'var(--paper)',
                        border: '1px solid var(--line)',
                        borderRadius: '8px',
                        boxShadow: '0 4px 16px rgba(34, 43, 40, 0.18)',
                        padding: '6px',
                        zIndex: 2147483647,
                        fontFamily: 'var(--font-ui)'
                    }}
                >
                    {usable.map(item => (
                        <button
                            key={item.key || item.label}
                            role="menuitem"
                            disabled={item.disabled}
                            title={item.title || ''}
                            style={{
                                display: 'block',
                                width: '100%',
                                textAlign: 'left',
                                padding: '8px 10px',
                                border: 'none',
                                borderRadius: '6px',
                                background: 'transparent',
                                color: item.tone === 'danger' ? 'var(--danger)' : 'var(--ink)',
                                fontFamily: 'var(--font-ui)',
                                fontSize: '13px',
                                cursor: item.disabled ? 'not-allowed' : 'pointer',
                                ...(item.disabled ? disabledStyle : {})
                            }}
                            onClick={() => {
                                if (item.disabled) return;
                                setOpen(false);
                                item.onSelect();
                            }}
                        >
                            {item.label}
                        </button>
                    ))}
                </div>
            )}
        </>
    );
}
