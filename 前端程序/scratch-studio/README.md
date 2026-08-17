# Scratch Studio（学生端工作台）

西瓜创客课程平台的 Scratch 图形化编程子应用。基于 `@scratch/scratch-gui@15.0.1`（AGPL-3.0-only）受控集成，
负责学生的 Scratch 工作台：加载初始 `.sb3`、编辑、绿旗运行、保存、提交；不负责课程权限、进度或管理台。

## 快速开始

```bash
# 安装依赖
npm install

# 开发模式（mock，无后端联调）
STUDIO_USE_MOCK=1 npm start
# Windows PowerShell：
#   $env:STUDIO_USE_MOCK="1"; npm start

# 真实接口模式（代理 /api 到本地 FastAPI:8000）
npm start
```

访问 `http://localhost:8602/?block_id=<课时块ID>`。

- **mock 模式**：`block_id` 任意值均可；初始项目为空，展示官方默认项目。
- **真实模式**：`block_id` 必须是当前学生有权限的 `scratch` 课时块 ID；否则后端返回 401/403/404。

## 构建

```bash
npm run build        # 产物在 dist/
```

## 接口契约

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/scratch/lesson-blocks/{block_id}` | 挑战 + 我的作品 + 最近判定 |
| GET | `/api/scratch/lesson-blocks/{block_id}/starter.sb3` | 初始项目 |
| PUT | `/api/scratch/projects/{project_id}` | 保存新版本（multipart `file`） |
| GET | `/api/scratch/projects/{project_id}/content.sb3` | 取回当前版本 |
| POST | `/api/scratch/lesson-blocks/{block_id}/submit` | 提交（无请求体） |
| GET | `/api/scratch/lesson-blocks/{block_id}/submissions` | 提交历史 |
| GET | `/api/scratch/lesson-blocks/{block_id}/demo.sb3` | 教师示范项目（**提交拿到结果后**才下发） |

完整契约见《开发文档/21a、ScratchStudio学生端-P0实施清单》§4（已对齐 21b）；
示范项目那条见《21g、Scratch示范项目录制与学生查看-开发交接》。

### 管理端预览 / 录制初始项目与示范项目

访问 `?mode=admin_preview&challenge_id=<挑战ID>&authoring_target=starter|demo`（教研权限）。
这条路**不复用**学生端端点：学生端要过课包发布、两道解锁闸、且挑战必须已发布
（草稿按 404），而教研要编的恰恰是草稿，草稿通常还没绑到任何课时块上——从设计上就
走不通。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/admin/scratch/challenges/{id}/studio-context` | 挑战 + 两个写回入口（形状对齐学生端 payload） |
| GET | `/api/admin/scratch/challenges/{id}/starter.sb3` | 取回初始项目（用响应里的 `challenge.starter_url`，不拼路径） |
| GET | `/api/admin/scratch/challenges/{id}/demo.sb3` | 取回示范项目（用 `authoring.demo_url`） |
| POST | `/api/admin/scratch/challenges/{id}/starter-project` | 存为本关初始项目（multipart `file`） |
| POST | `/api/admin/scratch/challenges/{id}/demo-project` | 存为本关示范项目（同一 multipart 形状） |

两种 target 的地址、可写判据、已存在判据收口在 `src/authoringTargets.js` 的表里，
组件不拼路径也不写 if-else——散着判断迟早出现「点了示范项目的保存却写进初始项目」。
示范项目的下载地址在 `authoring.demo_url` 而不是 `challenge` 段：后者的形状要与学生端
payload 对齐，而学生端永远不会有示范项目的下载地址。

`readonly: true` 恒为真——预览**绝不产生**学生作品或提交记录，所以这条栏没有保存/提交。
能不能写回只看 `authoring.can_write_starter` / `can_write_demo` 与对应的 `*_write_url`：
已发布时它们是 false / `null`，按钮自然点不动，提示文案直接用服务端的
`authoring.locked_reason`。前端不复述这套状态机。

mock 模式下这条路也能走：`npm run start:mock` 后访问
`?mode=admin_preview&challenge_id=1`；追加 `&authoring_target=demo` 录示范项目，
追加 `&mock_published=1` 可看已发布时按钮变灰的样子。

### 学生只读查看示范项目

访问 `?mode=student_demo&block_id=<课时块ID>&lesson_id=<课时ID>`。上下文复用学生详情
接口（`demo.available` / `demo.notice` 都在里面），装载走**独立的第三条支路**，绝不落进
「我的作品 / 初始项目」那个分支——那会把教师答案载入学生作品 VM，接着一次保存就把
答案写进作品历史。

这一屏没有保存、提交、存为初始项目，`canManageFiles={false}` 也关掉了整个「文件」菜单
（里面的「保存到你的电脑」不受 `canSave` 控制）。但要清楚：**这是移除入口，不是安全
边界**。学生拿到 `.sb3` 字节后本地解包就能看到全部答案，前端做什么都改不了这一点。
真正的边界只有后端那一条——提交拿到结果之前，`demo.sb3` 一个字节都不发。

## 关键实现说明

- **初始项目加载**：挂载官方 `<GUI>`（先展示官方默认项目），再 `vm.loadProject(初始 .sb3 的 ArrayBuffer)` 覆盖；优先 `project.content_url`（已有版本），否则 `challenge.starter_url`。
- **保存**：手动点「保存作品」→ `vm.saveProjectSb3()`（产出 `.sb3` Blob）→ `PUT /projects/{id}`（multipart + `X-CSRF-Token`）。失败不丢 VM 编辑状态，可重试。
- **提交**：`POST /submit`（无请求体），通过与否只信服务端返回的 `submission_status`，客户端不写任何"通过"标志。
- **云变量 / 社区 / 第三方扩展**：第一版默认关闭（`configFactory` 置空 `cloudVariables`，`canSave=false` 手动保存，不接社区）。

## 目录结构

```
scratch-studio/
├── package.json
├── webpack.config.js
├── index.html
└── src/
    ├── index.jsx                 # 入口：组 store + Provider
    ├── StudioApp.jsx             # 外壳：三种入口 → 加载对应 .sb3 + 布局
    ├── authoringTargets.js       # starter / demo 两种录制目标的地址与判据表
    ├── theme.js                  # 三条顶栏的共用样式（平台令牌）
    ├── gui/configFactory.js      # GUI 配置（复用 legacyConfig，禁云变量）
    ├── api/
    │   ├── types.js              # 接口契约类型（唯一事实来源）
    │   ├── client.js             # 真实 fetch（同域 + CSRF）
    │   ├── mockAdapter.js        # mock 实现
    │   └── index.js              # 门面：按 STUDIO_USE_MOCK 切换
    └── components/
        ├── SaveSubmitBar.jsx     # 学生：保存 / 提交
        ├── AuthoringBar.jsx      # 教研：录制 starter 或 demo
        └── DemoBar.jsx           # 学生：只读查看示范项目（一个写按钮都没有）
```

## 依赖与许可证

- `@scratch/scratch-gui@15.0.1`（AGPL-3.0-only，bundled 依赖 scratch-vm / scratch-paint / scratch-blocks / scratch-l10n）
- `react@^18` / `react-dom@^18` / `react-redux@^8` / `redux@^4`（peer，由本子应用提供）

AGPL-3.0 §13 网络交互条款与 Scratch 商标使用边界见《开发文档/21a、ScratchStudio学生端-P0实施清单》§1.2，对外发布前须定稿。
