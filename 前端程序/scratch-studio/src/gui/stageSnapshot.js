/**
 * 抓舞台当前画面，出一张 480×360 的 WebP Blob，用作作品封面（设计见《63》）。
 *
 * ## 为什么不是 `canvas.toDataURL()`
 *
 * 舞台画布的 WebGL 上下文 `preserveDrawingBuffer` 是 **false**（实测
 * `getContextAttributes()`）——绘制缓冲区在合成之后就被清空。此时随手调
 * `toDataURL()`，读到的是"这一帧画完了"还是"已经被清了"，取决于你这行代码落在
 * 浏览器帧循环的哪个位置。
 *
 * 实测里它**确实读出了正确的图**，而这正是它危险的地方：空载赌赢了。舞台上素材
 * 一多、机器一慢，学生就会拿到一张全黑或半截的封面，且不报任何错。这与判题那条
 * 竞态假红（见根 CLAUDE.md）是同一个形状：单跑必过、满载必挂。
 *
 * ## 不用赌的写法
 *
 * `scratch-render` 的 `requestSnapshot(cb)` 把回调压进队列，在 `draw()` **画完的
 * 同一次函数调用里**取 `canvas.toDataURL()` 再逐个回调——不存在那个时间窗。
 * 所以顺序必须是「先注册回调，再主动 `draw()`」，反过来就白画一帧。
 *
 * scratch-gui 自己的缩略图助手就是这么写的（产物里那段的错误日志文案是
 * `Project thumbnail save error`），但它没有从包入口导出，够不到，只能照抄。
 * 连 `forceTransparentPreview` 也一并抄：开着摄像头侦测时，视频图层不该被烤进封面。
 *
 * ## 失败一律返回 null
 *
 * 封面是装饰，作品是资产。截不到就不带这个字段，`.sb3` 照常保存，不提示也不报错
 * ——学生心智里"保存"就是保存作品，不该被一张截图挡住。
 */

/** 舞台原生尺寸，也是封面的输出尺寸。服务端按同样的尺寸重编码。 */
export const COVER_WIDTH = 480;
export const COVER_HEIGHT = 360;

/** 等一帧的上限。正常是下一次 draw 就回来（几毫秒），超过这个数说明渲染器卡住了。 */
const SNAPSHOT_TIMEOUT_MS = 2000;

/** 取 data URI：注册回调 → 主动画一帧 → 回调在这一帧里同步触发。 */
function requestStageDataUri (vm, timeout) {
    return new Promise(resolve => {
        const renderer = vm && vm.renderer;
        if (!renderer ||
            typeof renderer.requestSnapshot !== 'function' ||
            typeof renderer.draw !== 'function') {
            resolve(null);
            return;
        }
        const setVideoPreview = transparent => {
            if (typeof vm.postIOData !== 'function') return;
            try {
                vm.postIOData('video', {forceTransparentPreview: transparent});
            } catch (e) {
                // 没装视频侦测扩展时这条是空操作；真抛了也不该连累封面。
            }
        };

        // 超时后 resolve(null)：`requestSnapshot` 的回调留在队列里也无妨，它下次
        // draw 时会被调用，那时 settled 已经是 true，不会二次 resolve。
        //
        // **每条出口都必须把视频预览开关拨回去**（所以收口在 finish 里，不写在
        // 回调里）：漏掉超时那条，开着摄像头侦测的作品就会一直停在"透明预览"
        // 状态——一次没抓到图，舞台从此看着就是坏的。
        let settled = false;
        const finish = value => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            setVideoPreview(false);
            resolve(value);
        };
        const timer = setTimeout(() => finish(null), timeout);

        try {
            setVideoPreview(true);
            renderer.requestSnapshot(uri => finish(uri || null));
            renderer.draw();
        } catch (e) {
            finish(null);
        }
    });
}

/**
 * data URI → 480×360 的 WebP Blob。
 *
 * `requestSnapshot` 给的是 `toDataURL()` 无参的产物，即 PNG（480×360 约 15 KB）；
 * 重编码成 WebP q80 后约 4 KB。浏览器不支持 WebP 编码时 `toBlob` 会按规范回落成
 * PNG——体积大一些，但服务端反正要重编码一次，不影响正确性。
 */
function dataUriToCoverBlob (uri) {
    return new Promise(resolve => {
        const image = new Image();
        image.onload = () => {
            try {
                const canvas = document.createElement('canvas');
                canvas.width = COVER_WIDTH;
                canvas.height = COVER_HEIGHT;
                const context = canvas.getContext('2d');
                // 先铺白：舞台底色是白的，而 WebP/PNG 的空像素是透明的，
                // 不铺的话缩放边缘会渗出透明格子。
                context.fillStyle = '#ffffff';
                context.fillRect(0, 0, COVER_WIDTH, COVER_HEIGHT);
                context.drawImage(image, 0, 0, COVER_WIDTH, COVER_HEIGHT);
                canvas.toBlob(blob => resolve(blob || null), 'image/webp', 0.8);
            } catch (e) {
                resolve(null);
            }
        };
        image.onerror = () => resolve(null);
        image.src = uri;
    });
}

/**
 * 抓一张封面。**任何情况下都不抛**：抓不到返回 null，调用方原样往下走。
 *
 * @param {object} vm scratch-vm 实例
 * @param {{timeout?: number}} options
 * @returns {Promise<Blob|null>}
 */
export async function grabStageSnapshot (vm, {timeout = SNAPSHOT_TIMEOUT_MS} = {}) {
    try {
        const uri = await requestStageDataUri(vm, timeout);
        if (!uri) return null;
        return await dataUriToCoverBlob(uri);
    } catch (e) {
        return null;
    }
}
