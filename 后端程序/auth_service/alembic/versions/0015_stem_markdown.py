"""store problem stem, analysis and option content as Markdown source

Revision ID: 0015_stem_markdown
Revises: 0014_retire_offline_state

题干存储契约变更（2026-08-05 决策）：`problems.stem`、`problems.analysis`
和 `choice_options.content` 从"净化后的富文本 HTML"改为"Markdown 源码"。

改的原因：服务端按标签白名单净化 HTML 会把题面里的 `#include <iostream>`、
`vector<int>` 当成标签剥掉——这对一个 C++ 题库是致命的。改成存 Markdown 源码后
服务端不再碰内容，XSS 由渲染出口（Vditor + DOMPurify）负责。

转换范围是封闭的：写入时经过 `_sanitize_html` 的白名单过滤，库里只可能出现
p / br / strong / b / em / i / u / code / pre / ul / ol / li / blockquote / a
这 14 种标签，且除 `<a href>` 外不带任何属性。绝大多数行更是占位编辑器产出的
`<p>` + 转义文本 + `<br>` 这一种固定形状。

已知的有损项（数据量极小，接受）：
- `<ol>` 的序号还原成无序 `-`，原始编号无法从 HTML 推回；
- `<u>` 在 Markdown 里没有对应语法，只保留文字；
- 正文里本来就是字面量的 `*`、`_`、`#` 转换后会变成 Markdown 标记。
"""

import html
import re

from alembic import op
import sqlalchemy as sa


revision = "0015_stem_markdown"
down_revision = "0014_retire_offline_state"
branch_labels = None
depends_on = None

# 只有出现过白名单标签的值才需要转换，已经是纯文本/Markdown 的行原样跳过。
# 注意这不是幂等判据：正文里字面量的 `&lt;b&gt;` 转换后会变成真的 `<b>`，
# 再跑一次就会被当标签处理。alembic 按版本号只跑一次，这里不额外去重。
_LEGACY_TAG_RE = re.compile(r"</?(?:p|br|strong|b|em|i|u|code|pre|ul|ol|li|blockquote|a)\b[^>]*>", re.I)

_HTML_TO_MD = (
    (re.compile(r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>", re.I | re.S), "\n```\n\\1\n```\n"),
    (re.compile(r"<pre[^>]*>(.*?)</pre>", re.I | re.S), "\n```\n\\1\n```\n"),
    (re.compile(r"<code[^>]*>(.*?)</code>", re.I | re.S), "`\\1`"),
    (re.compile(r'<a[^>]*\bhref="([^"]*)"[^>]*>(.*?)</a>', re.I | re.S), "[\\2](\\1)"),
    (re.compile(r"<a[^>]*>(.*?)</a>", re.I | re.S), "\\1"),
    (re.compile(r"<(?:strong|b)>(.*?)</(?:strong|b)>", re.I | re.S), "**\\1**"),
    (re.compile(r"<(?:em|i)>(.*?)</(?:em|i)>", re.I | re.S), "*\\1*"),
    (re.compile(r"<li[^>]*>(.*?)</li>", re.I | re.S), "\n- \\1"),
    (re.compile(r"<blockquote[^>]*>(.*?)</blockquote>", re.I | re.S), "\n> \\1"),
    (re.compile(r"<br\s*/?>", re.I), "\n"),
    (re.compile(r"</(?:p|div|ul|ol|h[1-6])>", re.I), "\n\n"),
    (re.compile(r"<h([1-6])[^>]*>", re.I), lambda match: "\n" + "#" * int(match.group(1)) + " "),
    (re.compile(r"<[^>]+>"), ""),  # 剩余标签（含 <u>）只留文字
)


def _to_markdown(value: str | None) -> str | None:
    if not value or not _LEGACY_TAG_RE.search(value):
        return None
    text = value
    for pattern, replacement in _HTML_TO_MD:
        text = pattern.sub(replacement, text)
    # 实体还原必须放在剥标签之后：否则正文里字面量的 `&lt;p&gt;` 会先变成真标签再被吃掉。
    text = html.unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _to_html(value: str | None) -> str | None:
    """尽力而为的反向转换：只还原段落结构，Markdown 行内标记保持字面量。"""
    if not value or _LEGACY_TAG_RE.search(value):
        return None
    paragraphs = [block.strip() for block in re.split(r"\n{2,}", value) if block.strip()]
    if not paragraphs:
        return None
    return "".join(f"<p>{html.escape(block).replace(chr(10), '<br>')}</p>" for block in paragraphs)


def _convert(convert) -> None:
    connection = op.get_bind()
    for table, columns in (("problems", ("stem", "analysis")), ("choice_options", ("content",))):
        selected = ", ".join(columns)
        for row in connection.execute(sa.text(f"SELECT id, {selected} FROM {table}")).mappings().all():
            changes = {column: converted for column in columns if (converted := convert(row[column])) is not None}
            if changes:
                assignments = ", ".join(f"{column} = :{column}" for column in changes)
                connection.execute(
                    sa.text(f"UPDATE {table} SET {assignments} WHERE id = :row_id"),
                    {**changes, "row_id": row["id"]},
                )


def upgrade() -> None:
    _convert(_to_markdown)


def downgrade() -> None:
    _convert(_to_html)
