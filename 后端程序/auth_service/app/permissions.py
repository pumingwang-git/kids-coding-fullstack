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
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sqlalchemy import select

from .class_groups import active_class_teacher_assignments, active_student_ids_for_classes
from .models import AdminRole, AdminRoleCapability

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
# `admin` 只兼容历史数据与老会话，不得继续分配给新账号。
ASSIGNABLE_ROLE_NAMES = tuple(role for role in KNOWN_ROLE_NAMES if role != "admin")
ASSIGNABLE_ROLES = frozenset(ASSIGNABLE_ROLE_NAMES)

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

# 面向管理端的完整能力目录。顺序就是权限矩阵的稳定展示顺序。
CAPABILITY_CATALOG = {
    "content_edit": {"group": "内容", "label": "编辑内容", "description": "创建和编辑题目、试卷、课包与媒体。"},
    "content_review": {"group": "内容", "label": "审核内容", "description": "审核题目和试卷等正式内容。"},
    "class_read": {"group": "教学", "label": "查看班级", "description": "按数据范围查看班级及带班关系。"},
    "results_read": {"group": "教学", "label": "查看学情", "description": "按数据范围查看学员、作业和考试结果。"},
    "scratch_review": {"group": "教学", "label": "批改学生作品", "description": "按带班范围查看并批改学生 Scratch 作品。"},
    "announcements_send": {"group": "教学", "label": "发布班级公告", "description": "向权限范围内的班级发布公告。"},
    "help_respond": {"group": "教学", "label": "回复学生答疑", "description": "查看并回复带班范围内的学生答疑。"},
    "realtime_assist": {"group": "教学", "label": "发起实时答疑", "description": "在带班范围内邀请学生连线并编写讲解稿。"},
    "support_content_request": {"group": "安全", "label": "申请查看答疑正文", "description": "申请临时查看答疑正文或截图。"},
    "support_content_approve": {"group": "安全", "label": "批准答疑正文查看", "description": "批准有时限且可审计的答疑内容查看申请。"},
    "manage_classes": {"group": "教务", "label": "管理班级", "description": "新建班级并维护成员和带班关系。"},
    "manage_enrollments": {"group": "教务", "label": "管理课程开通", "description": "新增、撤销和调整课程资格。"},
    "export_class_insight": {"group": "数据", "label": "导出班级学情", "description": "导出权限范围内的学员姓名与成绩。"},
    "export_class_relationships": {"group": "数据", "label": "导出班级关系", "description": "导出权限范围内的成员与带班关系。"},
    "manage_admin_accounts": {"group": "安全", "label": "管理后台账号", "description": "新增、启停和重置后台账号。"},
    "manage_admin_roles": {"group": "安全", "label": "分配后台角色", "description": "改变后台账号的全局功能角色。"},
    "audit_events_read": {"group": "安全", "label": "查看审计日志", "description": "查询全局操作与安全审计记录。"},
}


def _capabilities(*allowed: str) -> dict[str, bool]:
    allowed_set = set(allowed)
    return {key: key in allowed_set for key in CAPABILITY_CATALOG}


# 管理端能力与菜单的唯一来源。数据范围仍由 ROLE_SCOPES/class_teachers 单独决定。
ROLE_CAPABILITIES = {
    SUPER_ROLE: _capabilities(*CAPABILITY_CATALOG),
    ACADEMIC_ADMIN_ROLE: _capabilities(
        "class_read", "results_read", "scratch_review", "announcements_send",
        "manage_classes", "manage_enrollments", "export_class_insight",
        "export_class_relationships", "support_content_request",
    ),
    TEACHER_ROLE: _capabilities(
        "class_read", "results_read", "scratch_review", "announcements_send",
        "export_class_insight", "export_class_relationships", "help_respond",
        "realtime_assist",
    ),
    ASSISTANT_ROLE: _capabilities(
        "class_read", "results_read", "scratch_review", "announcements_send",
        "export_class_insight", "export_class_relationships", "help_respond",
        "realtime_assist",
    ),
    "reviewer": _capabilities("content_review"),
    "editor": _capabilities("content_edit"),
    "admin": _capabilities("content_edit"),
}

# 页面标识是菜单协议的一部分；文案、图标和面包屑仍由 admin-layout.js 展示层维护。
ALL_MENU_PAGES = (
    "index.html", "questions.html", "papers.html", "exam-links.html",
    "courses.html", "learning-catalog.html", "nodes.html", "materials.html",
    "videos.html", "students.html", "enrollments.html", "classes.html",
    "teaching.html", "reports.html", "homework-results.html",
    "help-desk.html", "support-content.html",
    "accounts.html", "audit-logs.html",
)

# 不进菜单、但已认证账号可直接访问的占位页与提案层演示页。
NON_MENU_PAGES = (
    "notifications.html", "password-change.html",
    "building.html", "codes.html",
    "exam-links-demo.html", "teaching-demo.html",
)

# 页面从能力推导，角色表中不保存页面清单。空元组表示所有已认证后台账号都可见。
PAGE_CAPABILITY_ANY = {
    "index.html": (),
    "questions.html": ("content_edit", "content_review"),
    "papers.html": ("content_edit", "content_review"),
    "exam-links.html": ("content_edit", "content_review"),
    "courses.html": ("content_edit",),
    "learning-catalog.html": ("content_edit",),
    "nodes.html": ("content_edit",),
    "materials.html": ("content_edit",),
    "videos.html": ("content_edit",),
    "students.html": ("results_read",),
    "enrollments.html": ("manage_enrollments",),
    "classes.html": ("class_read", "manage_classes"),
    "teaching.html": ("class_read", "announcements_send"),
    "reports.html": ("results_read",),
    "homework-results.html": ("results_read",),
    "help-desk.html": ("help_respond", "support_content_request"),
    "support-content.html": ("support_content_request", "support_content_approve"),
    "accounts.html": ("manage_admin_accounts", "manage_admin_roles"),
    "audit-logs.html": ("audit_events_read",),
}


def pages_for_capabilities(capabilities: Mapping[str, bool]) -> tuple[str, ...]:
    """Derive stable menu pages from the effective capability set."""
    return tuple(
        page
        for page in ALL_MENU_PAGES
        if not PAGE_CAPABILITY_ANY[page]
        or any(capabilities.get(key, False) for key in PAGE_CAPABILITY_ANY[page])
    )


ROLE_MENUS = {
    role: pages_for_capabilities(capabilities)
    for role, capabilities in ROLE_CAPABILITIES.items()
}

ROLE_ALLOWED_PAGES = {
    role: tuple(dict.fromkeys((
        *ROLE_MENUS[role],
        *NON_MENU_PAGES,
        *(
            ("scratch-submissions.html", "scratch-review.html")
            if ROLE_CAPABILITIES[role]["scratch_review"] else ()
        ),
    )))
    for role in KNOWN_ROLE_NAMES
}


@dataclass(frozen=True)
class AuthorizationSnapshot:
    """Effective role policy used by routes and the management frontend."""

    role_key: str
    role_label: str
    scope: str
    scope_label: str
    scope_note: str
    revision: int
    capabilities: Mapping[str, bool]
    menus: tuple[str, ...]
    allowed_pages: tuple[str, ...]
    is_system: bool
    is_protected: bool
    is_assignable: bool

    def allows(self, capability: str) -> bool:
        return capability in CAPABILITY_CATALOG and bool(self.capabilities.get(capability, False))


def _scope_note(role_key: str, scope: str) -> str:
    if role_key in ROLE_SCOPE_NOTES:
        return ROLE_SCOPE_NOTES[role_key]
    return {
        GLOBAL_SCOPE: "可以看到全部班级与全部学生。",
        CLASS_SCOPE: "只能看到有效带班关系对应班级的学生。",
        NO_SCOPE: "不涉及学生数据。",
    }[scope]


def _snapshot_from_values(
    *,
    role_key: str,
    role_label: str,
    scope: str,
    revision: int,
    enabled_capabilities: set[str],
    is_system: bool,
    is_protected: bool,
    is_assignable: bool,
) -> AuthorizationSnapshot:
    capabilities = MappingProxyType(_capabilities(*enabled_capabilities))
    menus = pages_for_capabilities(capabilities)
    allowed_pages = tuple(dict.fromkeys((
        *menus,
        *NON_MENU_PAGES,
        *(("scratch-submissions.html", "scratch-review.html") if capabilities["scratch_review"] else ()),
    )))
    return AuthorizationSnapshot(
        role_key=role_key,
        role_label=role_label,
        scope=scope,
        scope_label=SCOPE_LABELS[scope],
        scope_note=_scope_note(role_key, scope),
        revision=revision,
        capabilities=capabilities,
        menus=menus,
        allowed_pages=allowed_pages,
        is_system=is_system,
        is_protected=is_protected,
        is_assignable=is_assignable,
    )


def authorization_snapshot(db, admin) -> AuthorizationSnapshot:
    """Load one request-scoped authorization snapshot; unknown roles fail closed."""
    cached = getattr(admin, "_authorization_snapshot", None)
    if cached is not None and cached.role_key == admin.role:
        return cached

    role = db.get(AdminRole, admin.role) if db is not None else None
    if role is not None and role.deleted_at is None:
        if role.key == SUPER_ROLE:
            enabled = set(CAPABILITY_CATALOG)
            scope = GLOBAL_SCOPE
        else:
            enabled = set(db.scalars(
                select(AdminRoleCapability.capability_key).where(
                    AdminRoleCapability.role_key == role.key
                )
            ))
            scope = role.scope
        snapshot = _snapshot_from_values(
            role_key=role.key,
            role_label=role.label,
            scope=scope,
            revision=role.revision,
            enabled_capabilities=enabled,
            is_system=role.is_system,
            is_protected=role.is_protected,
            is_assignable=role.is_assignable,
        )
    elif admin.role in ROLE_CAPABILITIES:
        # Compatibility for migration rollback and direct unit tests without a seeded catalog.
        snapshot = _snapshot_from_values(
            role_key=admin.role,
            role_label=ROLE_LABELS[admin.role],
            scope=ROLE_SCOPES[admin.role],
            revision=1,
            enabled_capabilities={
                key for key, allowed in ROLE_CAPABILITIES[admin.role].items() if allowed
            },
            is_system=admin.role in {SUPER_ROLE, "admin"},
            is_protected=admin.role in {SUPER_ROLE, "admin"},
            is_assignable=admin.role != "admin",
        )
    else:
        snapshot = _snapshot_from_values(
            role_key=admin.role,
            role_label=admin.role,
            scope=NO_SCOPE,
            revision=0,
            enabled_capabilities=set(),
            is_system=False,
            is_protected=False,
            is_assignable=False,
        )
    setattr(admin, "_authorization_snapshot", snapshot)
    return snapshot


def role_options(db, *, assignable_only: bool = False, include_retired: bool = False) -> list[dict]:
    """Return role policies in their stable management order."""
    query = select(AdminRole).order_by(AdminRole.sort_order, AdminRole.created_at, AdminRole.key)
    if not include_retired:
        query = query.where(AdminRole.deleted_at.is_(None))
    if assignable_only:
        query = query.where(AdminRole.is_assignable.is_(True))
    roles = list(db.scalars(query))
    result = []
    for role in roles:
        enabled = (
            set(CAPABILITY_CATALOG)
            if role.key == SUPER_ROLE
            else set(db.scalars(
                select(AdminRoleCapability.capability_key).where(
                    AdminRoleCapability.role_key == role.key
                )
            ))
        )
        snapshot = _snapshot_from_values(
            role_key=role.key,
            role_label=role.label,
            scope=GLOBAL_SCOPE if role.key == SUPER_ROLE else role.scope,
            revision=role.revision,
            enabled_capabilities=enabled,
            is_system=role.is_system,
            is_protected=role.is_protected,
            is_assignable=role.is_assignable,
        )
        result.append({
            "value": role.key,
            "label": role.label,
            "description": role.description,
            "scope": role.scope,
            "scope_label": snapshot.scope_label,
            "scope_note": snapshot.scope_note,
            "capabilities": dict(snapshot.capabilities),
            "menus": list(snapshot.menus),
            "allowed_pages": list(snapshot.allowed_pages),
            "revision": role.revision,
            "is_system": role.is_system,
            "is_protected": role.is_protected,
            "is_assignable": role.is_assignable,
            "deleted_at": role.deleted_at,
        })
    return result


def assignable_role(db, role_key: str, *, for_update: bool = False) -> AdminRole | None:
    query = select(AdminRole).where(
        AdminRole.key == role_key,
        AdminRole.deleted_at.is_(None),
        AdminRole.is_assignable.is_(True),
    )
    if for_update:
        query = query.with_for_update()
    return db.scalar(query)


def ensure_admin_role_catalog(session_factory) -> None:
    """Seed missing built-in definitions for create_all-based test databases."""
    with session_factory() as db:
        existing = set(db.scalars(select(AdminRole.key)))
        for index, role_key in enumerate(KNOWN_ROLE_NAMES):
            if role_key in existing:
                if role_key == SUPER_ROLE:
                    role = db.get(AdminRole, role_key)
                    role.scope = GLOBAL_SCOPE
                    current = set(db.scalars(
                        select(AdminRoleCapability.capability_key).where(
                            AdminRoleCapability.role_key == role_key
                        )
                    ))
                    for capability in set(CAPABILITY_CATALOG) - current:
                        db.add(AdminRoleCapability(role_key=role_key, capability_key=capability))
                continue
            role = AdminRole(
                key=role_key,
                label=ROLE_LABELS[role_key],
                scope=ROLE_SCOPES[role_key],
                is_system=True,
                is_protected=role_key in {SUPER_ROLE, "admin"},
                is_assignable=role_key != "admin",
                sort_order=index * 10,
            )
            db.add(role)
            for capability, allowed in ROLE_CAPABILITIES[role_key].items():
                if allowed:
                    db.add(AdminRoleCapability(role_key=role_key, capability_key=capability))
        db.commit()


def validate_admin_role(role: str) -> str:
    """校验管理员角色写入值，并返回原值供调用方直接赋值。"""
    if role not in KNOWN_ROLES:
        allowed = "、".join(KNOWN_ROLE_NAMES)
        raise ValueError(f"非法管理员角色 {role!r}；合法取值：{allowed}。")
    return role


def validate_assignable_admin_role(role: str) -> str:
    """校验网页管理端可分配的角色，拒绝仅供历史兼容的 ``admin``。"""
    validate_admin_role(role)
    if role not in ASSIGNABLE_ROLES:
        allowed = "、".join(ASSIGNABLE_ROLE_NAMES)
        raise ValueError(f"不可分配的管理员角色 {role!r}；可选值：{allowed}。")
    return role


def is_super(admin) -> bool:
    return admin.role == SUPER_ROLE


def is_editor(admin) -> bool:
    """能写内容（题目/试卷/课包/视频）。super_admin 豁免。"""
    return has_capability(admin, "content_edit")


def is_reviewer(admin) -> bool:
    """能审核。super_admin 豁免（单管理员环境下否则流程走不完，见 M2 决策）。"""
    return has_capability(admin, "content_review")


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
    scope = authorization_snapshot(db, admin).scope
    if scope == GLOBAL_SCOPE:
        return None
    if scope != CLASS_SCOPE:
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
    """学员名册读取能力；范围收窄由 ``visible_student_ids`` 负责。"""
    return has_capability(admin, "results_read")


def has_capability(admin, capability: str, db=None) -> bool:
    """读取角色能力；未知角色或未知能力一律拒绝。"""
    if capability not in CAPABILITY_CATALOG:
        return False
    snapshot = getattr(admin, "_authorization_snapshot", None)
    if snapshot is not None and snapshot.role_key == admin.role:
        return snapshot.allows(capability)
    if db is not None:
        return authorization_snapshot(db, admin).allows(capability)
    return bool(ROLE_CAPABILITIES.get(admin.role, {}).get(capability, False))


def can_review_student_work(admin) -> bool:
    return has_capability(admin, "scratch_review")


def can_export_class_insight(admin) -> bool:
    """Return whether the admin role reaches the class-insight export gate.

    This is intentionally distinct from the per-class scope check.  An
    assistant has the role-level route capability so a request for a class is
    rejected as an indistinguishable scope ``404``; content-only roles fail
    the feature gate with ``403`` regardless of the requested class.
    """
    return has_capability(admin, CLASS_INSIGHT_EXPORT_CAPABILITY)


def exportable_class_ids(admin, db) -> set[int] | None:
    """Return classes this admin may export, using the export-specific scope.

    ``None`` means globally visible.  Class-scoped staff may export only
    active ``teacher`` assignments; an assistant relationship therefore
    intentionally produces an empty export scope for that class.
    """
    scope = authorization_snapshot(db, admin).scope
    if scope == GLOBAL_SCOPE:
        return None
    if scope != CLASS_SCOPE:
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
    return has_capability(admin, "manage_enrollments")


def can_manage_classes(admin) -> bool:
    """班级主数据与成员/带班关系只允许教务和超管维护。"""
    return has_capability(admin, "manage_classes")
