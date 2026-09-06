# DESIGN.md — 启程学堂设计系统

> 版本 2.0 · 2026-08-14 · 覆盖**学生端**（`前端程序/study-blog-vue`，Vue 3 + Vite）与**管理端**（`前端程序/study-blog-vue/public/admin`，原生 HTML/JS）。
> 两端共享同一套品牌 token（纸白 + 薄荷绿 + 水獭），学生端扩展出「少儿专区 + 沉浸式课时/考试」，管理端收敛为「高密度工具台」。本文件可直接被 AI 编程代理消费。

---

## 1. Visual Theme & Atmosphere（视觉主题与氛围）

**品牌哲学**：纸白为底、薄荷绿为骨、水獭为引导角色。全站像一条清晰的学习路线图——先解释能力，再把人送往对应专区；登录后进入数据驱动工作台；课时与考试保持独立沉浸。少儿主题面向 8–14 岁学习者，活泼但不幼儿化。

**两端气质差异**（同源、不同密度）：

| 维度 | 学生端（面向学习者） | 管理端（面向内容运营） |
|------|---------------------|------------------------|
| 关键词 | 亲和、路径感、留白、鼓励行动 | 高效、密集、可扫描、工具化 |
| 节奏 | 大区块、不对称圆角、焦点插画 | 窄边栏 + 紧凑表格 + 多弹窗 |
| 视觉层级 | 首屏 hero 占据主视觉 | 信息密度优先，弱化装饰 |
| 插画 | 水獭场景插画引导空状态/路径 | 无插画，线性图标 + 文字 |

**核心视觉特征关键词**：纸白底 / 薄荷绿主色 / 不对称圆角 / 衬线标题 + 无衬线正文 / 水獭引导角色。

**光影与质感**：偏扁平 + 细边框 + 微阴影（不发光）。少儿壳层顶栏用轻微毛玻璃（`backdrop-filter: blur(16px)`）；管理端整体不透明、强调边框分区。

---

## 2. Color Palette & Roles（调色板与角色）

### 2.1 全站基础色（两端共享）

```css
:root {
  --paper:  #f8f8f0; /* 页面底色 */
  --ink:    #222b28; /* 正文主色 */
  --accent: #2f806e; /* 品牌主色 / 主行动 / 链接 / 路径节点 */
  --mint:   #dcebe1; /* 薄荷底 / 选中背景 / CTA 底 */
  --cream:  #f2ead9; /* 奶油辅助 / 概念卡 / 强调面板 */
  --muted:  #68716d; /* 次级文字 */
  --line:   rgba(34, 43, 40, 0.14); /* 分隔线 / 边框 */
  --danger: #b95c50; /* 错误 / 高风险（须配文字，不可仅靠颜色） */
}
```

### 2.2 学生端扩展色

```css
/* 少儿专区（Kids Shell） */
--kids-sky:   #dcecff; /* 天空蓝：欢迎区/已开放专区大底色 */
--kids-blue:  #4d82c2; /* 功能蓝：次级行动/空状态图标/链接 */
--kids-coral: #ef6b4a; /* 珊瑚橙：当前导航/关注主状态 */
--kids-sun:   #f4bd5b; /* 阳光黄：规划说明等低强度提示 */
--kids-panel: #fdfdf8; /* 内容面板底色 */

/* 沉浸式课时/考试（exam.css） */
--accent-deep: #256355; /* 主色深变体（hover/按压） */
--line-strong: rgba(34, 43, 40, 0.28); /* 强分隔线 */
--warn:      #b9852f; /* 警告（注意：与管理端 #bf8d39 不一致，需统一） */
--re-color:  #8a5a9e; /* 主观题/评分专属标识色 */
--surface:   #fffefb; /* 答题面板表面 */
--editor-bg: #20292a; --editor-fg: #d8e2dc; /* 代码编辑器 */
```

### 2.3 管理端扩展色

```css
--warn: #bf8d39; /* 警告 tag（⚠ 与学生端 exam.css #b9852f 冲突，建议统一为单一 --warn） */
```

管理端表单校验使用一套独立的红色：错误边框 `#dc2626`（焦点环 `rgba(220,38,38,0.12)`）、错误文字 `#b91c1c`。与 `--danger #b95c50` 并存，用于「表单无效态」，两者职责不同。

### 2.4 深色模式（当前仅学生端启用，管理端无深色）

```css
:root.dark {
  --paper: #1d2823;  --ink: #edf4ee;
  --accent: #67b49c; /* 深色下提亮主色保证对比 */
  --mint: #355e4e;   --cream: #3f4a3a;
  --muted: #b4bdb7;  --line: rgba(237, 244, 238, 0.16);
  --danger: #e08a7c; --warn: #d9a94e;
  --surface: #232f29; /* 少儿壳层面板 #1e2c3b / 背景 #172230 */
}
```

### 2.5 语义色角色表

| 角色 | 学生端 | 管理端 | 用途 |
|------|--------|--------|------|
| 成功 | `--accent` / `#287156` | `--accent` | 已上线、通过、完成 |
| 警告 | `--warn #b9852f` | `--warn #bf8d39` | 待处理、规划中 |
| 错误 | `--danger #b95c50` | `--danger` + 校验红 `#dc2626` | 失败、无效输入 |
| 信息/规划 | `--muted` | `--muted` / `--kids-sun` | 筹备、说明 |

---

## 3. Typography Rules（排版规则）

### 3.1 字体族

```css
--font-display: "Noto Serif SC", "Songti SC", serif;   /* 标题 / 品牌字，衬线强调学习与阅读感 */
--font-body:    "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; /* 正文 */
--font-mono:    "DM Mono", "JetBrains Mono", Consolas, monospace; /* 序号 / 代码 / 紧凑标记 */
```

> 管理端正文栈更偏系统：`-apple-system, BlinkMacSystemFont, "Noto Sans SC", "Microsoft YaHei"`；mono 用 `ui-monospace, SFMono-Regular, Menlo`。建议两端统一到上表 `--font-mono`。

### 3.2 字号层级表（学生端）

| 层级 | Font Size | Weight | Line Height | Letter Spacing | 用途 |
|------|-----------|--------|-------------|----------------|------|
| Display Hero | `clamp(42px, 5.4vw, 72px)` | 900 | 1.13 | -0.045em | 门户/专区首屏 h1 |
| H1 | `clamp(42px, 5.5vw, 63px)` | 500 | 1.25 | -2px | 通用页面主标题 |
| H2 / Section | `clamp(30px, 4vw, 48px)` | 800 | 1.25 | -0.035em | 区块标题 |
| H3 | `23px` | 700 | 1.2 | — | 卡片/条目标题 |
| Lead | `17px` | 400 | 1.85 | — | 首屏引导语 |
| Body | `14px` | 400 | 1.65–1.85 | — | 正文 |
| Small / Meta | `12–13px` | 500–700 | 1.6 | — | 说明、元信息 |
| Eyebrow / Kicker | `11–13px` | 900 | — | 0.08em | 分区眉题（mono） |

### 3.3 字号层级表（管理端，密度更高）

| 层级 | Font Size | Weight | 用途 |
|------|-----------|--------|------|
| 页面标题 h1 | `26px` | 500（衬线） | 页头标题 |
| 区块标题 h2/h3 | `18px / 16px` | 500 / 700 | 弹窗头 / 卡片头 |
| 正文 | `13px` | 400 | 表格、表单 |
| 辅助/表头 th | `11px` | 500 | 列头、说明 |
| 标签 tag | `11px` | 800 | 状态标签 |

**设计哲学**：学生端用大字号 + 宽松行高制造「呼吸感」；管理端用 11–13px + 紧凑行高制造「信息密度」。标题统一衬线、正文统一无衬线，字重用 700–900 做层次，避免依赖字号差异。

---

## 4. Component Stylings（组件样式）

### 4.1 按钮（Buttons）

**学生端 · 主/次行动（胶囊）**
```css
.primary-action, .secondary-action { min-height:48px; padding:12px 20px; border-radius:999px; font-size:14px; font-weight:900; }
.primary-action { background:var(--accent); border:1px solid var(--accent); color:#fff; }
.primary-action:hover { transform:translateY(-2px); box-shadow:0 12px 24px rgba(47,128,110,0.20); }
.secondary-action { background:transparent; border:1px solid var(--line); color:var(--ink); }
```

**学生端 · 基础按钮（方形）**
```css
.button { min-height:46px; padding:12px 18px; border:0; border-radius:4px; font-size:14px; font-weight:800; }
.button-primary { background:var(--accent); color:#fff; }
.button:hover { transform:translateY(-2px); }  /* 位移仅作辅助，须同时有颜色/边框变化 */
```

**管理端 · 工具按钮（紧凑）**
```css
.btn { padding:8px 14px; border:1px solid var(--line); border-radius:4px; background:transparent; color:var(--ink); font-size:13px; font-weight:800; }
.btn:hover { border-color:var(--accent); }
.btn.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
.btn.danger { color:var(--danger); }
.btn:disabled { opacity:0.5; cursor:not-allowed; }
```

### 4.2 卡片（Cards）

```css
/* 学生端 */
.card { padding:27px; border:1px solid var(--line); border-radius:8px;
        background:color-mix(in srgb, var(--paper) 82%, white);
        box-shadow:0 10px 24px rgba(34,43,40,0.06); }
/* 少儿大面板：不对称圆角 */
.continue-panel { padding:28px; border-radius:20px 8px 20px 8px; background:var(--kids-panel); }

/* 管理端 */
.card { padding:22px; border:1px solid var(--line); border-radius:8px;
        background:color-mix(in srgb, var(--paper) 85%, white);
        box-shadow:0 10px 24px rgba(34,43,40,0.06); }
```

### 4.3 输入框（Inputs）

```css
/* 学生端 */
input { padding:13px; border:1px solid var(--line); border-radius:4px; background:transparent; }
input:focus { border-color:var(--accent); box-shadow:0 0 0 3px rgba(47,128,110,0.12); }

/* 管理端 */
input, select, textarea { padding:9px 11px; border:1px solid var(--line); border-radius:4px; }
input:focus, select:focus, textarea:focus { border-color:var(--accent); box-shadow:0 0 0 3px rgba(47,128,110,0.12); }
input.input-invalid { border-color:#dc2626; box-shadow:0 0 0 3px rgba(220,38,38,0.12); }
```

### 4.4 导航（Navigation）

| 端 | 桌面 | 移动 |
|----|------|------|
| 学生端·门户 | 顶栏 + 底部 2px 下划线活跃态 | 折叠菜单（汉堡按钮） |
| 学生端·专区 | 248px 左侧栏，活跃项实底 `--area-accent` | ≤800px 隐藏侧栏，固定四项底部导航 |
| 管理端 | 232px 左侧栏（一级可折叠 + 二级虚线缩进），活跃项 `--accent` 实底白字 | — |

### 4.5 徽标 / 标签（Badges / Tags）

```css
.tag { display:inline-block; padding:2px 8px; border-radius:999px; background:var(--mint); color:var(--accent); font-size:11px; font-weight:800; }
.tag.gray   { background:rgba(104,113,109,0.12); color:var(--muted); }
.tag.warn   { background:rgba(191,141,57,0.14);  color:var(--warn); }
.tag.danger { background:rgba(185,92,80,0.14);   color:var(--danger); }
/* 学生端状态胶囊 */
.status-live { background:#fff; color:#287156; } .status-planning { color:var(--muted); }
```

### 4.6 弹窗 / 抽屉（Modals / Drawers）

```css
/* 管理端 Modal */
.modal-mask { background:rgba(34,43,40,0.5); z-index:100; }
.modal { width:min(1280px,94vw); max-height:88vh; background:var(--paper); border-radius:10px;
         box-shadow:0 24px 60px rgba(34,43,40,0.28); }
.modal 进入动画：opacity 0→1 + translateY(14px)→0 + scale(0.98)→1，0.22s ease。

/* 管理端 Drawer（右侧抽屉，用于详情） */
.drawer-mask / .drawer-foot 复用 modal 的遮罩与层级。
```

---

## 5. Layout Principles（布局原则）

### 5.1 间距系统

基数 **4px**，常用阶梯：`8 / 12 / 18 / 20 / 28 / 40px`；区块纵向间距学生端 `72–100px`，管理端 `16–22px`。

### 5.2 栅格与容器

| 容器 | 宽度 | 备注 |
|------|------|------|
| 学生端基础 `--content-width` | 1120px | 旧门户页 |
| 学生端门户/专区 `portal-section` | 1180px | 两侧 gutter 64px（移动 16px） |
| 学生端管理端侧栏 | 248px / 232px | kids-shell / admin sidebar |
| 页边距 `--page-gutter` | 48px → 32px → 14–16px | 桌面 / 平板 / 手机 |

### 5.3 布局模式

- **学生端**：`主内容 + 路径图`、`主专区 + 规划专区`、`说明 + 顺序列表` 等不对称两栏组合，突出主路径；禁止把所有能力压成等宽卡片。
- **管理端**：`侧栏 + 顶栏 + 内容` 三段式；内容区 `.content` padding `26px 28px 60px`；复杂编排用「左目录树 + 中内容块 + 独立编辑弹窗」。

---

## 6. Depth & Elevation（深度与层级）

### 6.1 阴影系统

```css
--shadow-sm:   0 2px 8px rgba(34,43,40,0.06);   /* 细边框卡片 */
--card-shadow: 0 10px 24px rgba(34,43,40,0.08);  /* 默认卡片 */
--hover-shadow:0 12px 24px rgba(47,128,110,0.20); /* 主行动 hover（品牌色轻阴影） */
--modal-shadow:0 24px 60px rgba(34,43,40,0.28);  /* 弹窗 */
--drop-shadow: 0 14px 15px rgba(34,43,40,0.14);  /* 插画投影 */
```

### 6.2 表面层级

`background(--paper)` → `surface(--surface/--kids-panel)` → `elevated(card)` → `overlay(modal-mask)`。学生端少儿顶栏为半透明毛玻璃层（`rgba(255,255,255,0.58) + blur(16px)`）。

### 6.3 Z-index 规范

```
10  内容内浮层
30  app-header（学生端顶栏）
50  kids-bottom-nav（移动底导航）
100 modal-mask / drawer-mask（管理端弹窗遮罩）
```

### 6.4 毛玻璃

仅学生端少儿壳层顶栏与移动底导航使用 `backdrop-filter: blur(16px–18px)`；管理端不使用。

---

## 7. Do's and Don'ts（设计规范与禁忌）

### Do's

1. 状态必须**同时用文字**表达（「已开放」「规划中」「正在筹备」），颜色不是唯一信号。
2. 图标统一走 `AppIcon.vue` 线性 SVG：`currentColor`、圆角端点、描边 1.8、`fill:none`，配 `aria-label` 或文字。
3. 复用 `assets/` 水獭插画服务欢迎、路径、空状态与规划状态；每个主要区块只出现一个焦点角色。
4. 空状态用 `.honest-empty`（图标/插画 + 简短原因 + 下一步行动），不伪造数据填满空白。
5. 键盘焦点 `2px–3px` 外轮廓（`outline: 3px solid color-mix(in srgb, var(--accent) 70%, white); outline-offset:3px`）。
6. 管理端高密度内容保持「列头 muted 11px + 正文 13px」，让表格可快速扫描。
7. 新增专区/分类/课程类型/标签一律走后台配置，不硬编码前端白名单。
8. 尊重 `prefers-reduced-motion: reduce`，关闭非必要动画。

### Don'ts

1. 不要把所有容器都做成胶囊；胶囊仅用于主行动、登录入口、短状态标签。
2. 不要把 `--warn` 写两个值（学生端 `#b9852f` vs 管理端 `#bf8d39`），必须统一。
3. 不要用 emoji 或混入风格不一致的图标库替代 AppIcon。
4. 不要在未具备真实数据前把「规划中」模块标记为已完成或伪造内容。
5. 不要用强烈发光/霓虹阴影，品牌阴影克制（≤ `0.28` 透明度）。
6. 不要仅靠颜色区分对错（学生端 `.option.correct/.wrong` 须同时有边框 + 背景 + 符号）。
7. 管理端不要把「编辑课时」与「编辑内容块」合并进一个弹窗（两者是独立弹窗 + 独立脏检查）。
8. 不要产生横向滚动；长中文文本须在 390px 宽度下正常换行。

---

## 8. Responsive Behavior（响应式行为）

### 8.1 断点

| 断点 | 行为 |
|------|------|
| `≤ 980px` | 学生端 portal-hero 单列；路径图收窄居中 |
| `≤ 800px` | 学生端隐藏桌面侧栏→移动底部导航；门户导航折叠；网格转单列 |
| `≤ 640px` | 继续学习卡片隐藏封面图（`.cc-cover{display:none}`） |
| `≤ 620px` | 管理端弹窗内容改单列、padding 收紧 |
| `≥ 桌面` | 学生端两栏不对称布局，管理端三段式 |

### 8.2 触摸目标

最小 `38px`（少儿紧凑行动），标准 `44–48px`（主行动、导航项）。

### 8.3 折叠策略

- 学生端：卡片网格 → 单列；`.area-showcase`/`.dual-loop`/`.portal-bridge` 两栏 → 单列。
- 管理端：`.form-grid` 两栏 → 单列；`.split` 两栏 → 单列；表格横向滚动包裹。
- 移动底部导航预留 `safe-area-inset-*`，内容区底部预留约 `104px`。

### 8.4 字体缩放

手机端首屏标题从 `clamp(42px,5.4vw,72px)` 收敛到 `clamp(36px,11vw,52px)`；正文保持 14–17px 不缩。

---

## 9. Agent Prompt Guide（AI 代理提示指南）

### 9.1 Quick Reference

- 品牌 token 以 `:root` 为准，禁止另起色值；学生端额外可用 `--kids-*` 系列，管理端可用 `--warn`。
- 学生端：标题衬线 `Noto Serif SC`、正文 `Noto Sans SC`、mono `DM Mono`；管理端可回退系统字体栈。
- 圆角：控件 4px、卡片 8px、少儿大面板 `20px 8px 20px 8px`、胶囊 999px。
- 阴影：默认 `0 10px 24px rgba(34,43,40,0.08)`；主行动 hover 用品牌色 `rgba(47,128,110,0.20)`。
- 深色模式仅学生端生效；管理端保持浅色。

### 9.2 Component Prompts（可直接复制）

1. **学生端主行动按钮**："按 DESIGN.md 生成一个 primary-action 胶囊按钮，min-height 48px、圆角 999px、背景 var(--accent)、hover 上移 2px 并出现品牌色阴影 0 12px 24px rgba(47,128,110,0.20)。"
2. **少儿专区卡片**："生成 continue-panel 风格面板，padding 28px、圆角 20px 8px 20px 8px、背景 var(--kids-panel)、边框 rgba(55,87,123,0.12)。"
3. **管理端数据表格**："生成管理端 table，正文 13px、表头 th muted 11px letter-spacing 0.5px、单元格 padding 11px 10px、行 hover 背景 rgba(47,128,110,0.04)。"
4. **管理端状态标签**："生成 tag 标签，胶囊圆角 999px、padding 2px 8px、字号 11px 字重 800，支持 gray/warn/danger 三种变体。"
5. **空状态**："生成 honest-empty 空状态：线性图标圆底 + 简短原因 + 下一步行动按钮，配色 var(--kids-blue)。"
6. **管理端弹窗**："生成 modal，遮罩 rgba(34,43,40,0.5) z-index 100，内容区 10px 圆角 + 阴影 0 24px 60px rgba(34,43,40,0.28)，头部标题 18px 衬线。"
7. **表单焦点态**："生成输入框，默认边框 var(--line)，focus 时边框 var(--accent) + 3px 光环 rgba(47,128,110,0.12)，圆角 4px。"

### 9.3 Iteration Guide（迭代建议）

1. 先读 `src/styles.css` 与 `public/admin/admin.css` 的 `:root`，确认可用 token 再动手。
2. 学生端新增样式优先走 `<style scoped>` 复用全局变量，不重复定义色值。
3. 管理端改动只改 `admin.css`，避免把样式写进各 html 内联，破坏复用。
4. 深色模式改学生端时同步补 `:root.dark` 覆盖，管理端不涉深色。
5. 新增颜色先问「是否已有 token 覆盖」，优先 `color-mix(in srgb, var(--accent) N%, ...)` 派生而非新增色值。
6. 触及「开放策略/内容块/考试」等既有交互时，先读对应 `.js`/`.vue` 的脏检查与校验逻辑，避免只改样式破坏状态。
7. 布局一律验证 390px / 768px / 桌面三档，禁止横向滚动。
8. 任何图标新增必须复用 AppIcon 线性 SVG，不得引入第三套图标库或 emoji。
9. 提交前用 `git diff` 核对是否动了业务常量或硬编码白名单（前端不得维护专区/分类白名单）。
10. 涉及 Scratch Studio 子应用时，注意其独立 React 技术栈与 Scratch 品牌紫，仅做容器壳层适配，不改其内部主题。

---

## 附：评审发现（待统一项）

| # | 问题 | 现状 | 建议 |
|---|------|------|------|
| 1 | `--warn` 双值 | 学生端 `#b9852f` / 管理端 `#bf8d39` | 统一为单一 `--warn`（推荐 `#b9852f`） |
| 2 | mono 字体栈分裂 | 学生端 `DM Mono` / 管理端 `ui-monospace` | 统一为 `--font-mono` 一条 |
| 3 | 容器宽度双轨 | `--content-width:1120px` 与门户 `1180px` 并存 | 统一以 1180px 为准或新增 `--content-wide` |
| 4 | 管理端无深色模式 | 仅学生端有 `:root.dark` | 明确管理端浅色为有意约束，暂不扩展 |
| 5 | 管理端校验红独立 | `#dc2626/#b91c1c` 与 `--danger` 并存 | 保留分工，但建议抽 `--danger-strong` token |
| 6 | 少儿壳层硬编码蓝 | `rgba(55,87,123,...)` 散落多处 | 抽 `--kids-ink-line` 等 token |
| 7 | Scratch Studio 品牌隔离 | React 子应用自带 Scratch 紫 | 明确为「嵌入式第三方视觉边界」 |

---

## 10. 数学星球独立应用契约

### 10.1 页面方向

- 数学星球是 `/math-studio/` 下的独立 Vue 应用，不嵌入主站学习壳层；主站工具箱只负责在新标签页启动。
- 首页采用截图参考中的简洁活动入口：品牌标题居中，24 点是唯一可玩的主卡，旁边只放诚实的“更多数学任务”筹备卡；统计记录压缩在卡片下方，不做大面积仪表盘。
- 大厅中的 24 点卡片直接进入游戏台，默认使用“自由练习 + 热身”设置，不再经过独立选择页。
- 游戏台右上角提供简洁设置按钮；点击后用浮层选择玩法与难度，应用后重开本轮。结果页继续承接结算与下一步动作。

### 10.2 视觉与交互规则

- 颜色以纸白、薄荷绿、天空蓝、珊瑚橙为主，并保留深墨绿文字；不得把界面做成单一蓝紫或纯装饰性渐变主题。
- 水獭只使用项目已有位图资产；正式控件统一使用 Lucide 线性图标，不用 emoji 代替按钮图标。
- 任务、模式、难度使用大目标控件；最小触摸目标 44px。状态反馈必须同时使用文字、图标和颜色。
- 四张数字牌和运算台必须有稳定尺寸，答题状态变化不能引发布局跳动；390px、768px、桌面三档均不得横向溢出。
- 支持清晰键盘焦点、`aria-live` 状态播报和 `prefers-reduced-motion`；儿童向动效应短促并服务于操作反馈。
- 数据区域直接呈现最高分、累计局数、正确率和最佳连对；离线状态要明确告知“可继续游戏、稍后同步”。
