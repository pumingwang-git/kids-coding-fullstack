import React, {useEffect, useState} from 'react';
import {createPortal} from 'react-dom';
import {ensureMenuBarSlot, setStudioTone, setStudioDebugHidden} from '../gui/menuBarSlot';
import {rowStyle, fallbackBarStyle} from '../theme';

/**
 * 平台操作条的外壳：把内容渲染进 Scratch 原生菜单栏内部的槽位。
 *
 * 拿不到槽位（GUI 还没挂载完 / 升级后结构变了）时**退回独立横条**——内容一模一样，
 * 只是回到"上下两层"的老样子。升级 GUI 最坏结果是退回今天，不是白屏。
 *
 * tone 决定身份色带：'admin' 教研、'readonly' 只读、'student' 无色带。合并前这件事
 * 靠整条栏的薄荷底色，合并后没了底色，色带 + 栏内常驻标签接手。
 */
export default function StudioBar ({children, tone = 'student', hideDebug = false}) {
    const [slot, setSlot] = useState(null);

    useEffect(() => {
        setStudioTone(tone);
        return () => setStudioTone('student');
    }, [tone]);

    useEffect(() => {
        setStudioDebugHidden(hideDebug);
        return () => setStudioDebugHidden(false);
    }, [hideDebug]);

    useEffect(() => {
        let cancelled = false;
        let timer = null;
        // GUI 与本组件在同一次提交里挂载，effect 跑的时候菜单栏通常已经在了；
        // 但 GUI 内部有懒加载分支，所以给一段有限的重试而不是只试一次。
        // 重试也负责"槽位被 GUI 重渲染摘掉"的情况（isConnected 变 false）。
        const tick = () => {
            if (cancelled) return;
            const found = ensureMenuBarSlot();
            setSlot(prev => (prev === found ? prev : found));
            timer = setTimeout(tick, found ? 1000 : 100);
        };
        tick();
        return () => {
            cancelled = true;
            if (timer) clearTimeout(timer);
        };
    }, []);

    const row = <div style={rowStyle}>{children}</div>;
    if (slot && slot.isConnected) return createPortal(row, slot);
    return <div style={fallbackBarStyle}>{children}</div>;
}
