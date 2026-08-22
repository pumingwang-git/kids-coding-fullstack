/**
 * 立即读取当前标题，再订阅后续变更。
 *
 * React effect 按声明顺序执行；服务端标题可能已在这个订阅建立前 dispatch，
 * 所以不能只等待下一次 store 通知。
 */
export function subscribeProjectTitle (store, onTitle) {
    const sync = () => onTitle(store.getState().scratchGui.projectTitle);
    sync();
    return store.subscribe(sync);
}
