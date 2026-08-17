// Markdown 渲染单源：题目编辑器（questions.html）与整卷预览（papers.html）共用。
// 空位标记（\placeholder[key]{} / ___ / {{blank}}）统一渲染为可见填空条 .blank-mark，
// 只影响显示、不改源码；跳过 <pre>/<code> 内的内容，避免代码被误显示成空位。

// 与后端 schemas.py 的 BLANK_KEY_RE 严格对齐：容忍 placeholder/方括号/花括号之间的空白，
// 以及花括号内的任意非 {} 内容。MathLive 的 \placeholder{默认值} 语法会诱导把答案写进
// 花括号（如 \placeholder[port]{80}）——不认这些写法，原文会带着答案渲染到学生卷上。
export const BLANK_MARK_RE = /(\\placeholder\s*\[\s*([A-Za-z][A-Za-z0-9_-]{0,63})\s*\]\s*\{\s*[^{}]*\s*\})|(_{3,})|(\{\{blank\}\})/g;

export function markBlanksInHtml(html) {
  return html
    .split(/(<pre[\s\S]*?<\/pre>|<code[\s\S]*?<\/code>)/g)
    .map((segment, index) =>
      index % 2 === 1
        ? segment
        : segment.replace(BLANK_MARK_RE, (match, placeholder, key) =>
            key
              ? `<span class="blank-mark" data-key="${key}"></span>`
              : '<span class="blank-mark"></span>',
          ),
    )
    .join("");
}

// 题干配图的尺寸档位。载体是 Markdown 图片 alt 的尾部后缀——`![三角形|50%](src)`。
//
// 曾经用内联 HTML 的 `<img width>` 当载体，症状是"设完尺寸图就从编辑器里不见了"：
// Vditor 的 IR 模式对**行内** HTML 只给一个 span[data-type=html-inline] > code.vditor-ir__marker，
// 而这个 marker 被 Vditor 自己的 CSS 压成 width:0;height:0;overflow:hidden ——
// 根本不生成 <img> 元素，图看不见，也就再点不回来改第二次。只有图恰好独占一行时
// lute 才按 html-block 处理并附一份预览，所以这个 bug 表现成"时好时坏"。
// 连带的第二处伤害在后端：admin_questions.py 的 _MD_IMAGE_RE 只认 `![](...)`，
// 纯图题干一旦设过尺寸就派生不出 `[图片单选题]` 占位，列表标题会变成一整行 <img> 标签。
//
// 换成 alt 后缀之后两端都不用改解析器：marked 与 lute 都把 alt 原样放进 alt 属性，
// 由渲染出口的 DOMPurify 钩子统一翻成 width（见 installImageHooks），仍然只有一份实现。
// 编辑区不过那条管线，靠 admin.css 里按 [alt$="|50%"] 选择的四条规则生效。
//
// "小"与 CSS 里"未设尺寸"的默认值保持一致（admin.css / MarkdownBody.vue 各一条 25%）。
export const IMAGE_WIDTHS = [
  { label: "小", value: "25%" },
  { label: "中", value: "50%" },
  { label: "大", value: "75%" },
  { label: "满宽", value: "100%" },
];

// alt 尾部的尺寸后缀。只认档位里的四个值，不放行任意百分比：编辑区那侧是四条写死的
// CSS 规则，放行任意值就会出现"源码里写了 60%、编辑器不认"的不一致。
const ALT_SIZE_RE = new RegExp(`\\|\\s*(${IMAGE_WIDTHS.map((item) => item.value).join("|")})\\s*$`);

/** 拆开图片的 alt：`"三角形|50%"` → `{ text: "三角形", width: "50%" }`。没后缀时 width 为 ""。 */
export function splitImageAlt(alt) {
  const raw = String(alt ?? "");
  const hit = raw.match(ALT_SIZE_RE);
  if (!hit) return { text: raw, width: "" };
  return { text: raw.slice(0, hit.index).trimEnd(), width: hit[1] };
}

/**
 * 把源码里指向 src 的那张图改写成指定宽度；width 传空则退回不带后缀的 `![alt](src)`。
 * 两种写法都认：`![alt](src)` 与旧数据里的 `<img src="src" …>`（后者顺手迁到新写法上）。
 * **alt 正文跟着搬家**——丢了它，改一次尺寸就把无障碍文本抹掉了，而且作者不会发现。
 *
 * 已知取舍：同一张图在一段题干里出现两次时只改第一处。为此引入出现次数索引会让
 * 逻辑复杂一倍，而这种情况几乎不发生。
 */
export function rewriteImageWidth(source, src, width) {
  const escaped = src.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const markdownRe = new RegExp(`!\\[([^\\]]*)\\]\\(\\s*${escaped}\\s*\\)`);
  const tagRe = new RegExp(`<img\\b[^>]*src=["']${escaped}["'][^>]*>`, "i");
  // 用函数形式替换：alt 里的 `$&`、`$1` 在字符串形式下会被当成替换模式吃掉。
  const build = (rawAlt) => () => {
    const { text } = splitImageAlt(rawAlt);
    return `![${text}${width ? `|${width}` : ""}](${src})`;
  };
  const markdownHit = source.match(markdownRe);
  if (markdownHit) return source.replace(markdownRe, build(markdownHit[1]));
  const tagHit = source.match(tagRe);
  if (tagHit) {
    const alt = (tagHit[0].match(/\balt=["']([^"']*)["']/i) || [])[1] || "";
    return source.replace(tagRe, build(alt));
  }
  return source;
}

// 题干配图的合法 src：必须与后端 admin_media.media_relative_path() 拼出的形状一致。
const MEDIA_SRC_RE = /^\/media\/[0-9a-f]{2}\/[0-9a-f]{64}\.[a-z0-9]{1,8}$/i;

/**
 * 题干配图在渲染出口上的两件事，装成同一个钩子：
 *
 * 1. **尺寸**：把 alt 尾部的 `|50%` 翻成 width 属性，并从 alt 上摘掉。
 *    不摘的话读屏器会把"三角形竖线五十百分号"念出来，而 alt 存在的唯一理由就是被念。
 * 2. **src 白名单**：收紧到只放行同源 /media/ 配图。
 *    USE_PROFILES:{html:true} 默认就放行 <img src>，所以不加这道钩子图也能显示——
 *    但它同时放行了任意外链和 data:，这正是要堵的两件事：
 *      a. 外链图会在对方站点挂掉时集体图裂，还把每个学员的 IP 送给第三方；
 *      b. data: URI 是 base64 内联的变体，已经在设计上否掉（stem 上限 50000 字符，
 *         一张内联图就能撑爆一道题），从渲染层堵死比在编辑器里劝阻可靠。
 *
 * 两件事合在一个安装函数里是有意的：只剩一个调用点，就没有"某一端只装了一半"的余地。
 * 后台与学员端各持有一个 DOMPurify 实例（一个是 vendor 全局，一个是 npm 包），
 * 所以做成"传实例进来装钩子"，而不是在这里直接装——两边都必须调用它。
 */
export function installImageHooks(purify) {
  if (!purify || purify.__imageHooksInstalled) return purify;
  purify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName !== "IMG") return;
    // 尺寸后缀优先于旧数据里可能残留的 width 属性——源码里写着什么就以什么为准。
    const { text, width } = splitImageAlt(node.getAttribute("alt") || "");
    if (width) {
      node.setAttribute("width", width);
      if (text) node.setAttribute("alt", text);
      else node.removeAttribute("alt");
    }
    if (MEDIA_SRC_RE.test(node.getAttribute("src") || "")) return;
    // 只摘掉 src 而不删整个节点：留一个坏图图标，至少能看出"这里本来有张图"，
    // 而不是让一道题悄悄少掉一个图形。
    node.removeAttribute("src");
    node.setAttribute("data-blocked-src", "1");
  });
  purify.__imageHooksInstalled = true;
  return purify;
}

export function sanitizeRenderedHtml(html) {
  const marked = markBlanksInHtml(html);
  if (!window.DOMPurify) return marked;
  installImageHooks(window.DOMPurify);
  return window.DOMPurify.sanitize(marked, { USE_PROFILES: { html: true } });
}

// 只读渲染：把 Markdown 渲染进 container（Vditor.preview 是异步的，返回 Promise）。
// 调用方 await 之后才能对产物做二次加工（如教师卷把填空答案填回 .blank-mark）。
export async function renderMarkdown(container, markdown) {
  if (!window.Vditor) {
    container.textContent = "预览组件未加载，请检查本地 vendor 资源。";
    return false;
  }
  await window.Vditor.preview(container, markdown || "", {
    cdn: "/admin/vendor/vditor",
    mode: "light",
    transform: sanitizeRenderedHtml,
  });
  return true;
}
