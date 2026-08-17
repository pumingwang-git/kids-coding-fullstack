# 学习系统设计 Token

学习系统继承个人博客的视觉语言，但减少大面积留白，优先保证表单、课程与练习内容的可读性。

| 类别 | Token | 值 / 规则 |
| --- | --- | --- |
| 页面底色 | `--paper` | `#f8f8f0` |
| 主文字 | `--ink` | `#222b28` |
| 品牌色 | `--accent` | `#2f806e` |
| 浅绿色块 | `--mint` | `#dcebe1` |
| 辅助文字 | `--muted` | `#68716d` |
| 标题字体 | `--font-display` | Noto Serif SC, serif |
| 正文字体 | `--font-body` | Noto Sans SC, sans-serif |
| 代码/编号字体 | `--font-mono` | DM Mono, monospace |
| 圆角 | `--radius` | 8px；按钮保持 4px |
| 阴影 | `--shadow` | 0 10px 24px rgba(34, 43, 40, .08) |
| 间距 | `--space-*` | 8px 基准递进 |

按钮、卡片、输入框与反馈状态均在 `style.css` 中通过这些变量实现。深色模式只替换颜色变量，不改变信息层级。
