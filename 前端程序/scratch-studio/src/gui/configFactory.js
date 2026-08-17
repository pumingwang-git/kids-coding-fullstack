/**
 * Studio 的 GUI 配置工厂。
 * 复用官方 legacyConfig（自带默认项目缓存 + 官方素材 web store），
 * 仅做两处收口：
 *  1. 禁用云变量（第一版不开放，官方 cloudManagerHOC 因缺少 cloudVariables 而跳过）
 *  2. 保存不依赖官方自动保存链路（canSave=false），由 StudioApp 手动走 PUT
 */
import {legacyConfig} from '@scratch/scratch-gui';

export function configFactory () {
    const storage = legacyConfig.storage;
    // 第一版不开放云变量 / 公共社区
    storage.cloudVariables = undefined;
    return {storage};
}

export default configFactory;
