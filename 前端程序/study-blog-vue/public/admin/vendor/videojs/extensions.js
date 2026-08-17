// 后台播放器对 video.js 的扩展：截图按钮 + 画质切换菜单。
// 跟随 video.min.js（UMD）加载，把组件挂到 videojs 全局，videos.js 在
// videojs(fresh, {...}) 时通过 controlBar.children 引用。
//
// 截图：Canvas 抓 video 元素当前帧，导出 PNG 下载。
// 画质：菜单列出后端 play 接口返回的 variants，第一项「自动」(master.m3u8)，
//      点击切换 player.src() 到对应 playlist_url（VHS 自动接管新流），重新构造
//      items 让选中项对号入座。
const videojs = window.videojs;
const Button = videojs.getComponent("Button");
const MenuButton = videojs.getComponent("MenuButton");
const MenuItem = videojs.getComponent("MenuItem");

// 内联 SVG 图标（video.js 自定义按钮没有自带图标，control-text 是视觉隐藏的——
// 不加图标就只有空白可点区域）。填进 .vjs-icon-placeholder 即可显示。
const ICONS = {
  screenshot:
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h3l1.5-2.5h7L17 7h3a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.5"/></svg>',
  quality:
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 8.5h18"/><circle cx="8" cy="14.5" r="2"/><path d="M14 13h5M14 16h5"/></svg>',
};

// 给自定义按钮注入图标：Button 自己的 createEl 已生成 .vjs-icon-placeholder（空），
// 直接把 SVG 塞进 placeholder 即可。不要再绕 ClickableComponent.createEl——
// 那会让 createControlTextEl 查找链断裂（this.createControlTextEl is not a function）。
function fillIcon(el, iconSvg) {
  const icon = document.createElement("span");
  icon.className = "vjs-icon-placeholder";
  icon.innerHTML = iconSvg;
  const existing = el.querySelector(".vjs-icon-placeholder");
  if (existing) existing.replaceWith(icon);
  else el.appendChild(icon);
}

// ---- 截图（学 B 站：先暂停当前帧，延迟 150ms 等帧渲染稳定再截，截完恢复播放，
//      完成后弹「截图已保存」提示） ----
class ScreenshotButton extends Button {
  constructor(player, options) {
    super(player, options);
    this.controlText("截图");
  }
  createEl(tag, props, attributes) {
    const el = super.createEl(tag || "button", props, attributes);
    fillIcon(el, ICONS.screenshot);
    return el;
  }
  handleClick() {
    const tech = this.player_.tech(true);
    if (!tech) return;
    const videoEl = tech.el();
    if (!videoEl.videoWidth || !videoEl.videoHeight) return;
    const wasPlaying = !this.player_.paused();
    this.player_.pause(); // 暂停保证抓到的就是当前帧
    setTimeout(() => {
      const canvas = document.createElement("canvas");
      canvas.width = videoEl.videoWidth;
      canvas.height = videoEl.videoHeight;
      canvas.getContext("2d").drawImage(videoEl, 0, 0);
      canvas.toBlob((blob) => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `screenshot-${Date.now()}.png`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 0);
        // 提示「截图已保存」（页面通过 window.__videoToast 注入，没有就静默）
        if (typeof window.__videoToast === "function") {
          window.__videoToast("截图已保存", false);
        }
      }, "image/png");
      if (wasPlaying) this.player_.play();
    }, 150);
  }
}
ScreenshotButton.prototype.controlText_ = "截图";
videojs.registerComponent("ScreenshotButton", ScreenshotButton);

// ---- 画质切换 ----
function buildQualityItems(player, masterPlaylist, variants, selectedIndex) {
  const items = [];
  const autoItem = new MenuItem(player, {
    label: "自动",
    selected: selectedIndex === 0,
  });
  autoItem.handleClick = () => {
    player.options_.selectedIndex = 0;
    player.src({ src: masterPlaylist, type: "application/vnd.apple.mpegurl" });
    player.play();
    refreshQualityMenu(player);
  };
  items.push(autoItem);
  variants.forEach((v, i) => {
    const item = new MenuItem(player, {
      label: v.bitrate_kbps ? `${v.resolution} ${v.bitrate_kbps}k` : v.resolution,
      selected: selectedIndex === i + 1,
    });
    item.handleClick = () => {
      player.options_.selectedIndex = i + 1;
      player.src({ src: v.playlist_url, type: "application/vnd.apple.mpegurl" });
      player.play();
      refreshQualityMenu(player);
    };
    items.push(item);
  });
  return items;
}

// createItems 只在播放器创建时调用一次（video.js MenuButton 行为），切档后
// 必须手动重建菜单 items，否则选中标记不刷新（画质显示有误）。
function refreshQualityMenu(player) {
  const qb = player.qualityButton;
  if (qb && qb.menu) {
    qb.menu.removeChildren();
    qb.createItems().forEach((item) => qb.menu.addItem(item));
  }
}

class QualityButton extends MenuButton {
  constructor(player, options) {
    super(player, options);
    this.controlText("画质");
    player.qualityButton = this; // 供切档后刷新菜单
  }
  createEl(tag, props, attributes) {
    const el = super.createEl(tag || "button", props, attributes);
    fillIcon(el, ICONS.quality);
    return el;
  }
  createItems() {
    const p = this.player_;
    return buildQualityItems(
      p,
      p.options_.masterPlaylist,
      p.options_.variants,
      p.options_.selectedIndex ?? 0
    );
  }
}
QualityButton.prototype.controlText_ = "画质";
videojs.registerComponent("QualityButton", QualityButton);

// 暴露构造器供 videos.js 调用
window.__videojsExtensions = {
  ScreenshotButton,
  QualityButton,
  buildQualityItems,
};