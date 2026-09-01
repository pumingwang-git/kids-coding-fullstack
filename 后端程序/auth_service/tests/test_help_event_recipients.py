"""答疑事件收件人解析：反向查询必须与 `visible_class_ids()` 逐字一致，且不随管理员总数变慢。"""

from sqlalchemy import event, select
from test_exam import ADMIN_PASSWORD, build_app

from app.models import AdminRole, AdminUser, ClassGroup, ClassTeacher, Course
from app.permissions import admin_ids_visible_for_class, has_capability, visible_class_ids
from app.security import password_hash


def _forward_reference(db, class_id: int, capability: str) -> set[int]:
    """朴素正向解：遍历全部 active 管理员。慢，但它是判据的基准。"""
    return {
        admin.id
        for admin in db.scalars(select(AdminUser).where(AdminUser.status == "active")).all()
        if has_capability(admin, capability, db)
        and ((ids := visible_class_ids(admin, db)) is None or class_id in ids)
    }


def _seed(db, *, teachers: int, outsiders: int, globals_: int, no_cap: int) -> int:
    course = Course(title="收件人对账课")
    db.add(course)
    db.flush()
    target = ClassGroup(name="目标班", course_id=course.id, status="active")
    other = ClassGroup(name="别的班", course_id=course.id, status="active")
    db.add_all([target, other])
    db.flush()

    quiet = AdminRole(key="recipients_no_cap", label="无答疑权限", scope="class")
    db.add(quiet)

    def make(username, role):
        row = AdminUser(
            username=username,
            password_hash=password_hash.hash(ADMIN_PASSWORD),
            display_name=username,
            role=role,
        )
        db.add(row)
        db.flush()
        return row

    for i in range(teachers):
        db.add(ClassTeacher(class_id=target.id, admin_user_id=make(f"t{i}", "teacher").id,
                            role_in_class="teacher"))
    for i in range(outsiders):
        db.add(ClassTeacher(class_id=other.id, admin_user_id=make(f"o{i}", "teacher").id,
                            role_in_class="teacher"))
    for i in range(globals_):
        make(f"g{i}", "academic_admin")
    for i in range(no_cap):
        db.add(ClassTeacher(class_id=target.id, admin_user_id=make(f"n{i}", quiet.key).id,
                            role_in_class="teacher"))
    db.commit()
    return target.id


def test_reverse_lookup_matches_the_naive_forward_scan(tmp_path):
    """候选集收窄不得改变结论。

    收窄的依据是「本班在任带班人 ∪ 全局范围账号」是收件人的超集。这条用例就是那个
    论证的可执行版本：任何把候选缩过头的改动（比如漏掉全局范围账号、或把 ended_at
    的判断写反）都会让两侧对不上。
    """
    app = build_app(tmp_path)
    db = app.state.session_factory()
    try:
        class_id = _seed(db, teachers=3, outsiders=4, globals_=2, no_cap=2)
        expected = _forward_reference(db, class_id, "help_respond")
        actual = admin_ids_visible_for_class(db, class_id, capability="help_respond")
        assert actual == expected
        # 哨兵：别拦过头——本班三个教师必须在里面，别班四个必须不在。
        assert len(expected) >= 3
        outsider_ids = {
            row.id for row in db.scalars(
                select(AdminUser).where(AdminUser.username.like("o%"))
            ).all()
        }
        assert not (actual & outsider_ids)
    finally:
        db.close()


def test_recipient_lookup_cost_does_not_grow_with_admin_count(tmp_path):
    """SQL 条数必须与管理员总数无关。

    旧实现遍历全部 active 管理员、每人再查一次能力和范围，挂在每条消息和每次输入中
    提示上。判据不是「快一点」，是**增加二十个不相干的管理员，查询条数一条都不能多**。
    """
    def count_queries(db, class_id):
        seen = []
        engine = db.get_bind()

        def before(conn, cursor, statement, *args):
            seen.append(statement)

        event.listen(engine, "before_cursor_execute", before)
        try:
            admin_ids_visible_for_class(db, class_id, capability="help_respond")
        finally:
            event.remove(engine, "before_cursor_execute", before)
        return len(seen)

    app = build_app(tmp_path)
    db = app.state.session_factory()
    try:
        class_id = _seed(db, teachers=2, outsiders=1, globals_=1, no_cap=0)
        small = count_queries(db, class_id)
        for i in range(20):
            db.add(AdminUser(
                username=f"bulk{i}",
                password_hash=password_hash.hash(ADMIN_PASSWORD),
                display_name=f"bulk{i}",
                role="teacher",
            ))
        db.commit()
        large = count_queries(db, class_id)
        assert large == small, f"新增 20 个不相干管理员后查询数从 {small} 涨到 {large}"
    finally:
        db.close()
