# 后台第三方库（本地自托管）

`public/admin/` 是零构建的原生静态后台，第三方库不走 npm/打包，直接下发到本目录再用 `<script src>` 引入。
`public/` 会被 Vite 原样复制到 `dist/`，所以这里放什么，线上就跑什么。

**所有库必须本地自托管，不允许运行时请求外部 CDN。** 验收方式见下方「离线自查」。

| 目录 | 版本 | 许可证 | 来源 |
|---|---|---|---|
| `vditor/` | 3.11.2 | MIT | npm `vditor` |
| `dompurify/` | 3.4.13 | Apache-2.0 / MPL-2.0 | npm `dompurify` |
| `quill/` | 2.0.3 | BSD-3-Clause | jsDelivr |
| `codemirror/` | 5.65.16 | MIT | jsDelivr |

## vditor

Markdown 编辑器，用于题目录入的题干 / 解析字段，以及「预览整题」。

⚠ **`cdn` 选项必须显式设成 `/admin/vendor/vditor`**。Vditor 默认按
`https://unpkg.com/vditor@<version>/dist/...` 去拉 lute、图标、highlight.js、KaTeX 等子资源，
不设这个选项就是个隐形的外部 CDN 依赖。目录层级必须保持 `vditor/dist/…` 不变（内部按 `${cdn}/dist/...` 拼路径）。

已从上游 `dist/` 裁剪掉**未启用的渲染器**（约省 14MB）：
`abcjs`、`echarts`、`flowchart.js`、`graphviz`、`markmap`、`mathjax`、`mermaid`、`plantuml`、`smiles-drawer`。
另外只保留 `highlight.js` 的 `github` / `github-dark` 两个主题（上游有 76 个）、
`i18n` 的 `zh_CN` / `en_US`、`icons` 的 `ant`、`content-theme` 的 `light` / `dark`，
以及 KaTeX 字体的 `.woff` / `.woff2`（`.ttf` 是给 IE 的，已删）。

**如果以后要开启 mermaid 流程图或 MathJax，必须把对应子目录补回来**，否则功能会静默失效。
重新下发的方式：

```bash
npm pack vditor@<version>
```

解包后按上面的清单拷贝 `package/dist/` 的子集，并同步更新本文件的版本号。

## dompurify

渲染出口的 XSS 净化。题干 / 解析在数据库里存的是 **Markdown 源码**，后端不做输入净化
（Markdown 里 `<` 是合法内容，`#include <iostream>`、`vector<int>` 都会被误杀），
安全性由渲染端保证：Vditor 实例的 `preview.transform` 和 `Vditor.preview()` 的 `transform`
两个钩子都要接 `DOMPurify.sanitize`。

将来 Vue 学生端渲染题面时必须走同一套，漏一处就等于开了个存储型 XSS 的后门。

## 离线自查

改动本目录后，打开 `/admin/questions.html`，在 DevTools Network 面板过滤
`unpkg.com`、`jsdelivr`、`cdnjs`，确认**零外部请求**。
