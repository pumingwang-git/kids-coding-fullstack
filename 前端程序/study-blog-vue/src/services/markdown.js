// 学员端 Markdown 渲染出口。题干、选项、须知、解析全部走这里，别在组件里各渲染各的。
//
// 空位标记的正则**直接复用后台那份**：public/admin/admin-markdown.js 与后端
// schemas.py 的 BLANK_KEY_RE 已经严格对齐，再抄一份必然有一天对不上——
// 那时的症状是"老师预览看到的空位和学生卷上的不一样"。Vite 能把 public/ 下的
// 普通 ES 模块打进来，这条 import 是有意为之。

import DOMPurify from "dompurify";
import { marked } from "marked";
import { installImageHooks, markBlanksInHtml } from "../../public/admin/admin-markdown.js";

marked.setOptions({ gfm: true, breaks: true });

// 题干配图的 src 白名单 + alt 尺寸后缀，与后台同一份实现。学员端漏装这道钩子的后果
// 比后台严重：题面里一条外链就能把每个考生的 IP 发给第三方站点。
installImageHooks(DOMPurify);

/**
 * Markdown 源码 → 可安全插入 DOM 的 HTML。
 * 题干入库时不净化（否则 `#include <iostream>` 会被按标签剥掉），净化在渲染出口做。
 */
export function renderMarkdown(source) {
  const html = marked.parse(String(source ?? ""));
  return DOMPurify.sanitize(markBlanksInHtml(html), { USE_PROFILES: { html: true } });
}
