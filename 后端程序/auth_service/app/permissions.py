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
TEACHER_ROLE = "teacher"
ASSISTANT_ROLE = "assistant"
ACADEMIC_ADMIN_ROLE = "academic_admin"

# 顺序是面向人类的稳定展示顺序；集合用于所有程序判断。
KNOWN_ROLE_NAMES = (
    SUPER_ROLE,
    "editor",
    "admin",  # 0013 之前的历史录入员角色，仍须兼容。
    "reviewer",
    TEACHER_ROLE,
    ASSISTANT_ROLE,
    ACADEMIC_ADMIN_ROLE,
)
KNOWN_ROLES = frozenset(KNOWN_ROLE_NAMES)


def validate_admin_role(role: str) -> str:
    """校验管理员角色写入值，并返回原值供调用方直接赋值。"""
    if role not in KNOWN_ROLES:
        allowed = "、".join(KNOWN_ROLE_NAMES)
        raise ValueError(f"非法管理员角色 {role!r}；合法取值：{allowed}。")
    return role


def is_super(admin) -> bool:
    return admin.role == SUPER_ROLE


def is_editor(admin) -> bool:
    """能写内容（题目/试卷/课包/视频）。super_admin 豁免。"""
    return admin.role in EDITOR_ROLES or is_super(admin)


def is_reviewer(admin) -> bool:
    """能审核。super_admin 豁免（单管理员环境下否则流程走不完，见 M2 决策）。"""
    return admin.role in REVIEWER_ROLES or is_super(admin)


def visible_class_ids(admin, db) -> set[int] | None:
    """返回管理员可见班级；``None`` 表示全局不受限。

    E1 尚未落地 ``class_teachers``，因此教师与助教暂时看不到任何班级。教务和
    超管是全局学情角色；其余内容角色不因此获得学生数据范围。E2 只需把受限角色
    的空集合替换为班级关联查询，调用点的 ``None`` 语义保持不变。
    """
    del db  # E2 接入 class_teachers 查询后使用。
    if admin.role in {SUPER_ROLE, ACADEMIC_ADMIN_ROLE}:
        return None
    return set()


def visible_student_ids(admin, db) -> set[int] | None:
    """返回管理员可见学生；由班级范围推导，``None`` 同样表示不受限。"""
    class_ids = visible_class_ids(admin, db)
    if class_ids is None:
        return None
    # E1 没有 class_members 表；E2 在这里按 class_ids 查询在班学生。
    return set()
