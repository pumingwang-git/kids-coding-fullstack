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

E2 由 `class_teachers` 提供 teacher / assistant 的真实班级范围；全局角色返回 None，
其余角色返回空集合。
见《32、企业级学习平台开发路线图-增补裁决-2026-08-17》4.3。
"""
from __future__ import annotations

import logging

from .class_groups import active_class_teacher_assignments, active_student_ids_for_classes

logger = logging.getLogger(__name__)

SUPER_ROLE = "super_admin"
EDITOR_ROLES = frozenset({"editor", "admin"})
REVIEWER_ROLES = frozenset({"reviewer"})
TEACHER_ROLE = "teacher"
ASSISTANT_ROLE = "assistant"
ACADEMIC_ADMIN_ROLE = "academic_admin"

# 字典顺序就是管理端的稳定展示顺序；0013 之前的 admin 仍须兼容老会话与老数据。
ROLE_LABELS = {
    SUPER_ROLE: "超级管理员",
    "editor": "内容录入员",
    "admin": "历史内容录入员",
    "reviewer": "内容审核员",
    TEACHER_ROLE: "教师",
    ASSISTANT_ROLE: "助教",
    ACADEMIC_ADMIN_ROLE: "教务管理员",
}
KNOWN_ROLE_NAMES = tuple(ROLE_LABELS)
KNOWN_ROLES = frozenset(KNOWN_ROLE_NAMES)

# 每个角色能看到哪些学生数据。取值与 visible_class_ids() 的返回语义一一对应：
#   global → None（不受限）  class → 班级 ID 集合  none → 空集合
# 加角色时这里必须同步，test_permissions.py 有一条参数化测试盯着两者不许分叉。
GLOBAL_SCOPE = "global"
CLASS_SCOPE = "class"
NO_SCOPE = "none"

ROLE_SCOPES = {
    SUPER_ROLE: GLOBAL_SCOPE,
    "editor": NO_SCOPE,
    "admin": NO_SCOPE,
    "reviewer": NO_SCOPE,
    TEACHER_ROLE: CLASS_SCOPE,
    ASSISTANT_ROLE: CLASS_SCOPE,
    ACADEMIC_ADMIN_ROLE: GLOBAL_SCOPE,
}

# 学情 CSV 是带走学员姓名与成绩的数据出口，能力边界比普通班级读取更窄。
# assistant 保留在功能能力集合中，是为了让其针对具体班级走范围闸（404），
# 而不是把「本班只是助教」错误地暴露成角色级功能闸（403）。
CLASS_INSIGHT_EXPORT_ROLES = frozenset({
    SUPER_ROLE,
    ACADEMIC_ADMIN_ROLE,
    TEACHER_ROLE,
    ASSISTANT_ROLE,
})
CLASS_INSIGHT_EXPORT_CAPABILITY = "export_class_insight"

SCOPE_LABELS = {
    GLOBAL_SCOPE: "全局",
    CLASS_SCOPE: "限本班",
    NO_SCOPE: "不涉及学生数据",
}

# 面向人的说明，管理端直接展示，避免前端自备文案随着范围规则过期。
ROLE_SCOPE_NOTES = {
    SUPER_ROLE: "可以看到全部班级与全部学生。",
    "editor": "只做内容生产，不涉及任何学生数据。",
    "admin": "等同内容录入员，不涉及任何学生数据。",
    "reviewer": "只做内容审核，不涉及任何学生数据。",
    TEACHER_ROLE: "只能看到自己在任带班关系对应班级的学生。",
    ASSISTANT_ROLE: "只能看到自己在任协助关系对应班级的学生。",
    ACADEMIC_ADMIN_ROLE: "教务角色，可以看到全部班级与全部学生。",
}

# 管理端能力与菜单的唯一来源。前端只保留展示信息，权限交集由此处下发。
ROLE_CAPABILITIES = {
    role: {
        "class_read": ROLE_SCOPES[role] != NO_SCOPE,
        "results_read": ROLE_SCOPES[role] != NO_SCOPE,
        "scratch_review": role in ({SUPER_ROLE} | REVIEWER_ROLES),
        "manage_admin_roles": role == SUPER_ROLE,
        "manage_classes": role in {SUPER_ROLE, ACADEMIC_ADMIN_ROLE},
        "audit_events_read": role == SUPER_ROLE,
        "export_class_insight": role in CLASS_INSIGHT_EXPORT_ROLES,
    }
    for role in KNOWN_ROLE_NAMES
}

# 页面标识是菜单协议的一部分；文案、图标和面包屑仍由 admin-layout.js 展示层维护。
ALL_MENU_PAGES = (
    "index.html", "questions.html", "papers.html", "exam-links.html",
    "courses.html", "learning-catalog.html", "nodes.html", "materials.html",
    "videos.html", "students.html", "enrollments.html", "classes.html",
    "teaching.html", "reports.html", "homework-results.html",
    "accounts.html", "audit-logs.html",
)
ROLE_MENUS = {
    SUPER_ROLE: ALL_MENU_PAGES,
    ACADEMIC_ADMIN_ROLE: tuple(page for page in ALL_MENU_PAGES if page not in {"accounts.html", "audit-logs.html"}),
    TEACHER_ROLE: ("index.html", "students.html", "classes.html", "teaching.html", "reports.html", "homework-results.html"),
    ASSISTANT_ROLE: ("index.html", "students.html", "classes.html", "teaching.html", "reports.html", "homework-results.html"),
    "reviewer": ("index.html", "questions.html", "papers.html", "exam-links.html"),
    "editor": ("index.html", "questions.html", "papers.html", "exam-links.html", "courses.html", "learning-catalog.html", "nodes.html", "materials.html", "videos.html"),
    "admin": ("index.html", "questions.html", "papers.html", "exam-links.html", "courses.html", "learning-catalog.html", "nodes.html", "materials.html", "videos.html"),
}


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


def log_scope_denial(admin, resource_type: str, resource_id: int) -> None:
    """记录一次数据范围拒绝（《39、API错误码与分页排序规范》§6）。

    **只记日志，不决定响应。** 响应必须与该端点「资源不存在」的分支逐字一致，
    由调用点共用同一处 raise 抛出——返回 403 或换个文案，都等于告诉调用方
    「这条记录存在，只是不归你管」，那正是 E1 验收标准第 6 条要堵的泄露。

    不写 audit_events：一次 ID 遍历探测会产生成百上千条拒绝，写进审计表会淹没
    真正的授权变更记录（规范 §6.1）。日志里不得出现学生姓名、用户名或原始 IP。
    """
    logger.warning(
        "scope_denied role=%s admin_user_id=%s resource=%s:%s",
        admin.role,
        admin.id,
        resource_type,
        resource_id,
    )


def visible_class_ids(admin, db) -> set[int] | None:
    """返回管理员可见班级；``None`` 表示全局不受限。

    教师与助教只取 ``class_teachers.ended_at IS NULL`` 的关系。教务和超管是全局
    学情角色；其余内容角色不因此获得学生数据范围。受限角色必须传入数据库会话，
    遗漏会话直接报错，避免静默收窄为空集。
    """
    if admin.role in {SUPER_ROLE, ACADEMIC_ADMIN_ROLE}:
        return None
    if admin.role not in {TEACHER_ROLE, ASSISTANT_ROLE}:
        return set()
    if db is None:
        raise TypeError("受限班级范围查询必须提供数据库会话。")
    return {row.class_id for row in active_class_teacher_assignments(db, admin.id)}


def visible_student_ids(admin, db) -> set[int] | None:
    """返回管理员可见学生；由班级范围推导，``None`` 同样表示不受限。"""
    class_ids = visible_class_ids(admin, db)
    if class_ids is None:
        return None
    return active_student_ids_for_classes(db, class_ids)


def can_read_students(admin) -> bool:
    """判断角色是否具备学员数据读取能力；范围收窄由 ``visible_student_ids`` 负责。"""
    return ROLE_SCOPES.get(admin.role, NO_SCOPE) != NO_SCOPE


def can_export_class_insight(admin) -> bool:
    """Return whether the admin role reaches the class-insight export gate.

    This is intentionally distinct from the per-class scope check.  An
    assistant has the role-level route capability so a request for a class is
    rejected as an indistinguishable scope ``404``; content-only roles fail
    the feature gate with ``403`` regardless of the requested class.
    """
    return admin.role in CLASS_INSIGHT_EXPORT_ROLES


def exportable_class_ids(admin, db) -> set[int] | None:
    """Return classes this admin may export, using the export-specific scope.

    ``None`` means globally visible.  Class-scoped staff may export only
    active ``teacher`` assignments; an assistant relationship therefore
    intentionally produces an empty export scope for that class.
    """
    if admin.role in {SUPER_ROLE, ACADEMIC_ADMIN_ROLE}:
        return None
    if admin.role not in {TEACHER_ROLE, ASSISTANT_ROLE}:
        return set()
    if db is None:
        raise TypeError("导出班级范围查询必须提供数据库会话。")
    return {
        row.class_id
        for row in active_class_teacher_assignments(db, admin.id)
        if row.role_in_class == TEACHER_ROLE
    }


def can_export_class_insight_for_class(admin, db, class_id: int) -> bool:
    """Return the capability bit for a class overview response."""
    if not can_export_class_insight(admin):
        return False
    class_ids = exportable_class_ids(admin, db)
    return class_ids is None or class_id in class_ids


def can_manage_enrollments(admin) -> bool:
    """课程开通属于教务动作，内容编辑角色不因此获得资格管理权。"""
    return admin.role in {SUPER_ROLE, ACADEMIC_ADMIN_ROLE}


def can_manage_classes(admin) -> bool:
    """班级主数据与成员/带班关系只允许教务和超管维护。"""
    return admin.role in {SUPER_ROLE, ACADEMIC_ADMIN_ROLE}
