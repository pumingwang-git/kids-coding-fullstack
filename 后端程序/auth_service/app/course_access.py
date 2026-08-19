"""课时访问判定：学生端课程接口与视频播放接口共用的**唯一**入口。

为什么单独一个模块：这条规则将来要被 enrollments（开通资格）、学习有效期、
解锁规则依次改写。只要它散落在 routers/courses.py 与 routers/video_play.py 里各写一份，
接 enrollments 那天就一定会漏掉其中一个入口——漏掉的那个不会报错，只会静默放行。

当前阶段的规则：
1. 课包必须 published。draft / off_shelf 对学生一律**不存在**（404，不是 403——
   不泄露「有这么个课包但你看不了」）；
2. 开放策略（open_policy，2026-08-10 定稿替代 is_trial 复选框）：
   - whole（整节试看）：登录学员可看整节完整内容；
   - first_n（试看前 N 块）：第 1..N 个内容块开放，其余块锁定（逐块判定见 `lesson_block_open`）；
   - closed（不开放）/ video_minutes（二期）：默认拒绝。
3. 其余课时：**默认拒绝**（deny by default，理由见下）。

第 3 条是有意选的 deny by default，不是「先放开等以后收紧」。理由：放开容易、
收紧难，而收紧的那天不会有人重新审一遍所有入口。代价是本阶段演示需要把课时勾上
「试看」——一个复选框换一条不会忘记关的门。

E3a 的个人开通记录在 `_enrolled` 里统一查询，并实时比较 `opened_at` 与 `expires_at`
（实时判定而非依赖 status 物化，理由见《7、…-补丁说明》补丁五）。E3b 只补班级
来源，不改本判定入口；调用方签名不变，一处都不用动。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import (
    Course,
    CourseLesson,
    CourseLessonBlock,
    Enrollment,
    LessonBlockCompletion,
    User,
)
from .security import utcnow

OPEN_POLICIES = {"closed", "whole", "first_n", "video_minutes"}
UNLOCK_RULES = {"free", "sequential"}


class Access(str, Enum):
    GRANTED = "granted"  # 完整内容
    DENIED = "denied"    # 标题可见，内容不可见


def course_visible(course: Course | None) -> bool:
    """课包本身对学生是否存在。列表页与详情页统一用它。"""
    return course is not None and course.status == "published"


def lesson_policy(lesson: CourseLesson) -> str:
    """课时开放策略。旧数据兜底：迁移未跑或直接写旧字段时，is_trial 仍为真视为 whole。"""
    policy = lesson.open_policy
    if policy not in OPEN_POLICIES:
        return "whole" if lesson.is_trial else "closed"
    return policy


def enrollment_predicates(now: datetime):
    """开通资格的唯一谓词，单条与集合查询必须共用。"""
    return (
        Enrollment.status == "active",
        Enrollment.opened_at <= now,
        or_(Enrollment.expires_at.is_(None), Enrollment.expires_at >= now),
    )


def _enrolled(db: Session, user: User | None, course: Course) -> bool:
    """是否已开通该课包。

    资格始终按请求时刻实时判断，不能依赖异步任务把过期记录物化为 expired。
    E3a 的个人开通记录来自 ``enrollments``；E3b 只会新增来源记录，这里按任一
    有效记录授权，调用方不需要改签名。
    """
    if user is None:
        return False
    now = utcnow()
    return db.scalar(
        select(Enrollment.id).where(
            Enrollment.student_id == user.id,
            Enrollment.course_id == course.id,
            *enrollment_predicates(now),
        )
    ) is not None


def enrolled_course_ids(db: Session, user: User | None) -> set[int]:
    """返回该学生当前已开通的全部课包 id，资格口径与 ``_enrolled`` 一致。"""
    if user is None:
        return set()
    now = utcnow()
    return set(db.scalars(
        select(Enrollment.course_id).where(
            Enrollment.student_id == user.id,
            *enrollment_predicates(now),
        )
    ).all())


def lesson_access(db: Session, user: User | None, lesson: CourseLesson) -> Access:
    course = db.get(Course, lesson.course_id)
    if not course_visible(course):
        return Access.DENIED
    if user is None:
        return Access.DENIED
    # 整节试看：未开通也能看完整内容。first_n 不在这里放行——那是逐块口径。
    # video_minutes（视频试听 N 分钟）目前只是**二期契约**：字段/接口已预留，
    # 但播放层的时间限制尚未实现，一律按「不开放」处理，绝不放行——
    # 界面（管理端下拉）也没有暴露该选项，避免误导宣称已支持试听 N 分钟。
    if lesson_policy(lesson) == "whole":
        return Access.GRANTED
    return Access.GRANTED if _enrolled(db, user, course) else Access.DENIED


def lesson_block_open(db: Session, user: User | None, lesson: CourseLesson,
                      block_sort_order: int, granted: bool | None = None) -> bool:
    """内容块级访问判定（排序是 0..n-1 连续压实，见 0030 迁移与 reorder 接口）。

    完整解锁（整节试看 / 已开通）→ 全块开放；
    试看前 N 块（first_n）→ 前 trial_block_count 块开放，其余拒绝；
    其余策略（含 video_minutes 二期）→ 拒绝。
    """
    # ``granted`` 是调用方按课时缓存的真实 Gate A 结论；传错会静默放行，不能猜测。
    if granted is None:
        granted = lesson_access(db, user, lesson) is Access.GRANTED
    if granted:
        return True
    if lesson_policy(lesson) == "first_n":
        count = lesson.trial_block_count or 0
        return count > 0 and block_sort_order < count
    return False


# ---------------------------------------------------------------------------
# Gate B · 路径闸（2026-08-10 新增，《14、单课时学习界面-开发交接》第四节）
#
# 与上面的 Gate A（权限闸）正交，回答的是两个不同的问题：
#   Gate A  你有没有资格看这块      —— 商务决定（是否开通 / 试看策略），全课时统一
#   Gate B  按教学顺序轮到你学了吗  —— 教研决定（unlock_rule），逐块变化
# 合成一个 locked: bool 必然出错：学生看到锁不知道该去掏钱还是该去学习，
# 出口也完全不同（去开通页 / 回去学前面）。
# ---------------------------------------------------------------------------


def completed_block_ids(db: Session, user: User | None, lesson_id: int) -> set[int]:
    """本课时中该用户已完成的块 id 集合。

    一次查完再逐块判定，避免 block_unlocked 里对每个前置块各查一次（N+1）。
    未登录没有完成记录，直接返回空集。
    """
    if user is None:
        return set()
    return set(
        db.scalars(
            select(LessonBlockCompletion.block_id).where(
                LessonBlockCompletion.user_id == user.id,
                LessonBlockCompletion.lesson_id == lesson_id,
            )
        ).all()
    )


def block_unlocked(db: Session, user: User | None, lesson: CourseLesson,
                   block: CourseLessonBlock, ordered_blocks: list[CourseLessonBlock],
                   completed_ids: set[int], granted: bool | None = None) -> bool:
    """Gate B：unlock_rule=sequential 的块要求前面所有「必修且有权限」的块已完成。

    ordered_blocks 必须是本课时按 sort_order 升序的全部块（调用方已经查过一次，
    这里不重复查库）。

    两条不能省的排除规则，省掉任何一条都会把学生卡死：

    1. `required=False` 的选学块**不阻塞**。否则老师加一个「拓展阅读（选学）」，
       没人点它，后面的闯关块就永远开不了。
    2. `can_access=False` 的块**不能当前置条件**。否则 first_n=3 的未开通学生：
       第 4 块没权限 → 永远完成不了 → 第 5 块的 sequential 永远不满足 → 第 5 块
       显示成「顺序锁」并给出「回去学前面」的出口，而学生**根本没有权限去学第 4 块**
       ——死循环。排除之后这类学生看到的一律是权限锁，出口正确指向开通页。
    """
    if block.unlock_rule != "sequential":
        return True
    if user is None:
        return False  # 未登录不可能有完成记录，sequential 一律锁
    # 已经学完的块永远不再上锁。否则：老师中途把某块改成 sequential、或前置块的配置
    # 变动（required 改动、块被重排），学生**已经学完**的块会突然锁上并提示「回去学前面」
    # ——他已经学过了，把他赶回去毫无意义，界面上还会出现「已完成 + 锁定」的自相矛盾态。
    if block.id in completed_ids:
        return True
    for prev in ordered_blocks:
        if prev.sort_order >= block.sort_order:
            break
        if not prev.required:
            continue  # 坑 1：选学块不阻塞
        if not (granted or lesson_block_open(db, user, lesson, prev.sort_order, granted)):
            continue  # 坑 2：没权限的块不能当前置条件
        if prev.id not in completed_ids:
            return False
    return True


def block_gate(db: Session, user: User | None, lesson: CourseLesson,
               block: CourseLessonBlock, ordered_blocks: list[CourseLessonBlock],
               completed_ids: set[int], granted: bool | None = None) -> dict:
    """两道闸门的完整判定结果：{can_access, is_unlocked, lock_reason}。学生端 DTO 直接用它。

    **判定顺序不可颠倒**：没资格看的内容谈不上学习顺序。颠倒之后，未开通的学生会
    先撞上「完成前面的内容块」这条错误引导，而正确的出口是去开通课包。

    两个布尔字段各自如实回答自己那道闸门（即使另一道已经拦下），lock_reason 才是
    合成结论——前端只认 lock_reason，两个布尔是给管理端预览与排查用的。

    granted 由调用方传入（详情接口已经算过 lesson_access），省一次重复判定。
    """
    if granted is None:
        granted = lesson_access(db, user, lesson) is Access.GRANTED
    can_access = granted or lesson_block_open(db, user, lesson, block.sort_order, granted)
    is_unlocked = block_unlocked(db, user, lesson, block, ordered_blocks, completed_ids, granted)
    if not can_access:
        reason = "not_enrolled"
    elif not is_unlocked:
        reason = "sequential"
    else:
        reason = None
    return {"can_access": can_access, "is_unlocked": is_unlocked, "lock_reason": reason}


def block_lock_reason(db: Session, user: User | None, lesson: CourseLesson,
                      block: CourseLessonBlock, ordered_blocks: list[CourseLessonBlock],
                      completed_ids: set[int], granted: bool | None = None) -> str | None:
    """锁定原因快捷式：None=可学 / "not_enrolled"=权限锁 / "sequential"=顺序锁。"""
    return block_gate(db, user, lesson, block, ordered_blocks, completed_ids, granted)["lock_reason"]


def lesson_progress(ordered_blocks: list[CourseLessonBlock],
                    completed_ids: set[int]) -> dict:
    """课时学习进度。分母只数 required=True 的块（选学块完成了照样记录，但不计入）。"""
    required = [b for b in ordered_blocks if b.required]
    total = len(required)
    done = sum(1 for b in required if b.id in completed_ids)
    percent = 100 if total == 0 else round(done / total * 100)
    return {"total": total, "done": done, "percent": percent}


def lesson_unlocked(db: Session, user: User | None, lesson: CourseLesson) -> bool:
    """布尔快捷式，给目录树逐行标 unlocked 用（仅表示整节完整开放）。"""
    return lesson_access(db, user, lesson) is Access.GRANTED


def course_enrolled(db: Session, user: User | None, course: Course) -> bool:
    """课包级开通状态，详情页用来渲染「已开通 / 未开通」。"""
    return _enrolled(db, user, course)
