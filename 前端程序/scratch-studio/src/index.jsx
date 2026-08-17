import React from 'react';
import {createRoot} from 'react-dom/client';
import {Provider} from 'react-redux';
import {createStore, combineReducers} from 'redux';
import GUI, {
    guiReducers,
    buildInitialState,
    guiMiddleware,
    localesInitialState,
    initLocale
} from '@scratch/scratch-gui';
import configFactory from './gui/configFactory';
import StudioApp from './StudioApp';

// react-modal 无障碍要求：设置应用根节点
GUI.setAppElement('#root');

const config = configFactory();
const store = createStore(
    combineReducers(guiReducers),
    {
        locales: initLocale(localesInitialState, 'zh-cn'),
        scratchGui: buildInitialState(config)
    },
    // guiMiddleware 已由 Scratch GUI 内部用 compose(applyMiddleware(...)) 构造成
    // Redux enhancer。再把它传给 applyMiddleware 会把 enhancer 当普通 middleware，
    // Redux 随后调用 createStore.apply(...) 而白屏；官方 editor-state.tsx 也是直接传它。
    guiMiddleware
);

const container = document.getElementById('root');
const root = createRoot(container);
root.render(
    <Provider store={store}>
        <StudioApp />
    </Provider>
);

// AppStateHOC 会在官方独立编辑器启动时触发该状态转换。
// 本项目自行创建 store，因此需要显式发起默认项目加载；否则 loadingState
// 会永久停在 NOT_LOADED，StudioApp 等待编辑器就绪就会超时。
