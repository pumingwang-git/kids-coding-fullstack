# 项目约定

企业级学习平台。两端：`前端程序/study-blog-vue`（学生端 Vue 3 + Vite；管理端 `public/admin` 是**原生 HTML/JS**）、`后端程序/auth_service`（FastAPI + SQLAlchemy + Alembic）。

---

## 跑测试

```bash
cd 后端程序/auth_service && ./.venv/Scripts/python.exe -m pytest tests/xxx.py -q
```

必须用这个 venv，系统 python 没装 pytest。全量必须独占运行，开跑前确认没有其他会话正在跑 pytest。实测共收集 **999 条**，独占基线（2026-08-24）为 **1 failed / 997 passed / 1 skipped / 35 分 53 秒**，改动小时只跑相关文件。

此前两次并发期间的全量把 `test_class_migration.py` 报成失败 14 条，被误记为「既有欠账」并派生出一个不存在的修复任务。非独占跑出来的失败清单没有诊断价值。排查线索：`ScriptDirectory.from_config()` 会 import `alembic/versions/` 下每个迁移文件，多进程同时跑会撞 Windows **pycache** 文件锁，命中的正好是走 `command.*` 的那批用例。

**已知失败（本轮不要顺手改）**：`test_student_learning.py::test_unpublished_course_lesson_denied`——当前测试期望 `403`、实现返回 `404`；按范围闸规范，可能是测试期望过时而非代码有错，需专项裁决后再处理。

---

## 文档权威链

```
已落地代码/迁移/测试 > 专项设计与裁决 > 《32、增补裁决》 > 《30、路线图》 > 更早文档
```

阶段编号统一 `E0–E8`。讨论开发顺序、权限模型或阶段范围时**先读 32 再读 30**。

| 文档 | 内容 |
|---|---|
| 33 | ADR-001 身份与权限模型（双主体、§2.4 授权矩阵） |
| 34 | ADR-002 多组织维度暂不预留 |
| 36 | E0 权限矩阵与数据范围对账 |
| 37 | 审计事件字段规范 |
| 39 | API 错误码与分页排序规范 |
| 40 | 迁移回滚与种子数据规范 |
| 41 | 管理端账号管理范围裁决 |
| 42 | E2 班级模块任务分解 |

> ⚠️ **编号陷阱**：《E0-权限矩阵与数据范围对账》定稿是 **36**，草稿期曾暂编 32，而 32 已被《增补裁决》占用。**引用按标题判断，不要按编号**——代码里指向《32、…增补裁决》的链接是对的，别"顺手改成 36"。

**`开发文档/` 被 gitignore**，文档改动不进版本库，只在本地。

---

## 硬性纪律

- **`permissions.py` 是角色常量的唯一来源。** 判据：下面这条命令必须输出为空。
  ```bash
  grep -rn '"super_admin"\|"editor"\|"reviewer"' 后端程序/auth_service/app/routers/ | grep -v admin_auth.py
  ```
- **双主体不合并**：学员是 `users`，后台账号是 `admin_users`。`class_members` 指向前者，`class_teachers` 指向后者，不得互换。
- **不加组织维度**：`organization_id` / `tenant_id` / `campus_id` 一律禁止，空列预留也不行（ADR-002）。
- **关系表保留历史**：退班写 `left_at`、取消带班写 `ended_at`，不 DELETE。
- **管理端样式只改 `public/admin/admin.css`**，不要写进各 html 内联。
- **前端不得自备角色/状态/范围文案**，一律从接口取（源头在 `permissions.py`）。有静态契约测试盯着。
- **`app/student_tasks.py` 是学生任务派生状态的唯一来源。** 三套状态（`homework_phase` / `practice_phase` / `exam_phase`）和三份 `*_PHASE_LABELS` 都住在这里；考试时间窗只认 `routers/exam.py::_phase()`，`exam_phase` 只做分组不重算。教师端、报表、总览一律复用，不许另写一套。
- **判断作答是否仍开放，只能用 `student_tasks._attempt_is_open()`。** `paper_attempts.status` 是 cron 物化（`close_expired_attempts.py`，5 分钟一次），直接读 `status == "ongoing"` 会让早已过期的作答长期显示「进行中」。E4 新增代码里 grep 这条串必须只命中 `_attempt_is_open` 一处。
- **课包资格判定只有一份谓词**：`course_access.enrollment_predicates()`。单条判定走 `_enrolled()`，集合判定走 `enrolled_course_ids()`，不许在别处再写一遍时间窗。例外：`class_enrollment.revoke_for_membership()` 故意不带时间窗（退班要撤销 `opened_at` 在未来的记录），那里有注释和哨兵测试，**不许"顺手统一"**。
- **迁移测试一律 `upgrade(<待测 revision>)`，永不 `upgrade("head")`**（见《40》）。

### 权限拒绝的两类闸门（规范 39 §3）

| 闸门 | 含义 | 状态码 |
|---|---|---|
| 功能闸 | 角色根本没这项能力，与哪条资源无关 | `403` |
| 范围闸 | 有能力，但这条资源不在数据范围内 | `404`，与"不存在"**逐字相同** |

判断方法：把资源 ID 换成另一个，结论会变吗？不变=功能闸，会变=范围闸。范围拒绝走 `permissions.log_scope_denial()` 记日志，**不写 audit_events**。

---

## 已知陷阱

- **迁移链在 SQLite 上跑不通**（`0008_admin_auth` 用 `op.add_column` 加外键，SQLite 不支持 ALTER 约束）。测试历来用 `Base.metadata.create_all` 建库；要测某条迁移就 `create_all` + `alembic stamp <前一版>` 再单跑，见 `tests/test_class_migration.py`。
- **`alembic/env.py` 会用 `get_settings().database_url` 覆盖 `sqlalchemy.url`。** 测试里改连接串必须设 `DATABASE_URL` 环境变量 **并** `get_settings.cache_clear()`（它有 `lru_cache`），事后再 clear 一次。
- **登录会下发新的 CSRF token。** 测试辅助函数若在登录前取 token，后续所有写操作会停在 `require_csrf` 的 403 上——看着像被权限拦住，其实根本没走到权限判断。曾有测试因此"绿着但什么都没测到"。
- **`.env` 里可能是真实库**，别让测试跑上去。

---

## Git

- 提交信息用中文单行：`feat:` / `fix:` / `test:` / `docs:` / `chore:`，不写 body。
- **可能有多个会话并行改这个仓库。** 提交前先 `git status`，**只显式列出自己改的文件**，永远不要 `git add .` 或 `git stash`。
- 主分支是 `main`，本项目直接在 main 上提交。

---

## 工作方式

- 本项目默认**交付设计文档**，写到别人能照着实现的详细度；实现可以交给他人。
- 结论要有证据：跑命令、读代码，不靠印象。声称"已验证"前先真的跑一遍。
- 新写的守卫/约束要做**变异验证**——把它临时改成失效，确认测试会红，再改回来。只会通过的测试等于没有测试。
- 约束和守卫要有"别拦过头"的哨兵用例（如退班后可重新入班），它比拦截用例更容易写错。
