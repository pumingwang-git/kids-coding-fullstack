"""B 端角色常量与权限判定的唯一来源。

背景：`SUPER_ROLE` / `EDITOR_ROLES` / `REVIEWER_ROLES` 在 admin_questions、admin_papers、
admin_results、admin_videos、admin_courses 各抄了一份（第 5 份见课程模块）。抄得越多，
将来加一个角色就越可能漏改其中一处——这类漏改不会报错，只会静默放行或静默拒绝。

本文件收口。语义与既有实现保持一致（以 admin_questions.py 为准）：
- `EDITOR_ROLES` 不含 super_admin，`REVIEWER_ROLES` 也不含——super_admin 由
  `is_super()` 单独豁免，判定函数里再或上去。这样「谁是编辑」和「谁是超管」
  在读代码时是两件事，不会混成一个集合。
- `admin` 是上线前的历史角色，按 editor 兼容（0013 迁移已把存量数据转为 editor，
  常量保留是为了老会话与老数据不炸）。

E1 先定义 `visible_class_ids()` 的签名并铺调用点：teacher / assistant 暂时返回空集合，
全局角色返回 None；E2 落地 `class_teachers` 后只替换本文件内部查询。
见《32、企业级学习平台开发路线图-增补裁决-2026-08-17》4.3。
"""
from __future__ import annotations

SUPER_ROLE = "super_admin"
EDITOR_ROLES = frozenset({"editor", "admin"})
REVIEWER_ROLES = frozenset({"reviewer"})


def is_super(admin) -> bool:
    return admin.role == SUPER_ROLE


def is_editor(admin) -> bool:
    """能写内容（题目/试卷/课包/视频）。super_admin 豁免。"""
    return admin.role in EDITOR_ROLES or is_super(admin)


def is_reviewer(admin) -> bool:
    """能审核。super_admin 豁免（单管理员环境下否则流程走不完，见 M2 决策）。"""
    return admin.role in REVIEWER_ROLES or is_super(admin)
