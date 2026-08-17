# 学习系统认证服务

提供用户名/邮箱密码注册与登录、图片人机验证码、邮箱验证码验证、短期 JWT access cookie、轮换 refresh cookie、CSRF 校验、会话撤销、审计记录和限流。MFA 当前默认暂停，保留配置以便后续恢复。

## 本地启动

1. 创建并激活独立虚拟环境，安装 `pip install -r requirements.txt`。
2. 复制 `.env.example` 为 `.env`；开发环境不配置 SMTP 时会使用内存邮件发送器，便于测试，绝不会真实发信。
3. 运行 `uvicorn app.main:app --reload --port 8000`。
4. 运行 `alembic upgrade head` 后再启动服务；当前迁移版本包含 `0005_login_history`。

## 测试策略

日常开发采用“目标测试 + 最小回归”，不要求每实现一个独立功能就运行全部 `tests/`。

```powershell
# 只运行本次改动直接覆盖的测试文件
.\.venv\Scripts\python.exe -m pytest tests\test_attempt_source.py -q

# 只运行一个具体用例
.\.venv\Scripts\python.exe -m pytest tests\test_attempt_source.py::test_xxx -q

# 完整后端回归（功能完成、提交前或修改共享逻辑时执行）
.\.venv\Scripts\python.exe -m pytest -q
```

以下改动必须执行完整后端回归：数据库模型或 Alembic 迁移、认证与权限、中间件、共享依赖或服务层、公共 API 契约、配置/启动路径，以及一次功能开发完成后的最终验收。目标测试通过只说明直接受影响路径正常，不能替代完整回归、迁移演练或真实接口/浏览器验收。

## 异地 / 新 IP 登录检测

登录成功后，接口会先返回 Cookie；后台任务再记录一条 `login_history`。首次成功登录仅建立基线，不发送提醒。后续登录若 IP 从未出现，或 GeoIP 已识别且城市/地区从未出现，则写入 `anomaly=true` 并通过现有邮件 Outbox 发送告警；Outbox 失败可由 `python -m app.workers` 重试。

服务端只保存 IP HMAC，不保存明文 IP。`TRUSTED_PROXY_IPS` 必须只填写自有 Nginx/负载均衡的地址；由 `ProxyHeadersMiddleware` 在可信代理场景下规范化 `request.client`，业务代码不会直接采信浏览器伪造的 `X-Forwarded-For`。

面向中国用户时，优先配置 `IP2REGION_V4_DATABASE_PATH`（及可选的 `IP2REGION_V6_DATABASE_PATH`）为本地 `.xdb` 文件；中国 IP 会返回中文国家、省、市和运营商信息。`GEOIP_DATABASE_PATH` 保留为未命中时的 GeoLite2 City `.mmdb` 全球兜底。两类库都未配置或查库失败时，安全降级为仅比对 IP。Redis 可用时维护 `auth:known-locations:{user_id}` 90 天滚动集合加速比对，数据库历史仍是审计真相来源。

生产环境须将 `DATABASE_URL` 设为 PostgreSQL，运行 `alembic upgrade head`，配置 Redis、企业 SMTP、独立随机密钥、HTTPS 及精确的前端源。SQLite 与内存限流器仅用于本地开发。登录须先通过一次性图片验证码；注册不使用图片验证码，改由邮箱验证码完成账号激活。服务端只保存图片验证码答案 HMAC，5 分钟过期且最多尝试 5 次。SMTP 发送失败的 outbox 项可由 `python -m app.workers` 重试，连续失败 5 次后进入 `dead` 状态供监控处理。

## 泄露密码检查与密码历史

- 注册、密码重置和登录后的“修改密码”都会调用 HaveIBeenPwned Pwned Passwords 的 k-anonymity 接口：只发送密码 SHA-1 摘要的前 5 位，后缀在本地比对，完整密码与完整摘要均不离开本服务；前缀结果内存缓存 24 小时。默认 fail-open（泄露库不可用时放行并记日志），`PWNED_CHECK_STRICT=true` 时改为 fail-closed（返回 503）。国内网络不稳定时可将 `PWNED_API_BASE_URL` 指向保持 `/range/{prefix}` 接口的自建镜像。
- 被泄露的密码会被拒绝（400，提示泄露次数）；注册页前端也会做一次同接口的非阻断性提示。
- 新密码不得与当前密码或最近 `PASSWORD_HISTORY_COUNT`（默认 5）次使用过的密码相同；被替换的密码以 Argon2id 哈希存入 `password_history` 表，超出数量自动裁剪。
- 新增两步改密：`POST /api/auth/password-change/request`（需登录 + CSRF + 当前密码）向已绑定邮箱发送一次性验证码；`POST /api/auth/password-change` 还需该验证码。成功后撤销包括当前设备在内的所有旧会话，并签发一个新的当前会话。
- 生产环境必须设置 `PWNED_CHECK_ENABLED=true` 与 `PWNED_CHECK_STRICT=true`；无法稳定连接官方服务时，请使用受控的 HTTPS 镜像或本地数据源。
- 升级：`alembic upgrade head`（当前迁移版本包含 `0006_password_history`）。

## B 端管理后台认证

- 独立于学生端的管理员体系：`admin_users` / `admin_sessions` / `slider_captcha_challenges` 表（Alembic `0008_admin_auth`）。
- 登录使用**自研滑块验证码**（`app/slider_captcha.py`，SVG 生成零依赖）：背景图挖拼图孔、拼图块独立成图，水平偏移 x 是唯一秘密（Fernet 加密入库），容差 ±6px，一次性、5 分钟过期、最多尝试 5 次——与图片验证码同一套安全策略。
- 会话与学生端同模式但完全隔离：独立 cookie（`admin_access_token` / `admin_refresh_token` / `admin_csrf_token`）、JWT issuer/audience 独立、refresh 轮换 + 重用检测整族撤销、CSRF double-submit、登录限流 + 渐进锁定、审计事件 `admin_` 前缀（`audit_events.admin_user_id`）。
- 接口：`GET /api/admin/csrf`、`GET /api/admin/captcha-slider`、`POST /api/admin/login`、`POST /api/admin/refresh`、`GET /api/admin/me`、`POST /api/admin/logout`。
- 创建管理员：`ADMIN_USERNAME=xxx ADMIN_PASSWORD=yyy python -m app.create_admin`（幂等，可更新密码/角色）。
- 前端页面：`study-blog-vue/public/admin/`（登录页 `login.html` + 后台首页 `index.html`，纯 HTML/CSS/JS）。
