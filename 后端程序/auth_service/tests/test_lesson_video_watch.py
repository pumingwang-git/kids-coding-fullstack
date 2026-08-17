"""视频观看时长服务端记账的端到端回归（POST …/blocks/{id}/watch）。

《20、视频观看时长服务端记账-设计-2026-08-13》§10 验收清单第 3/7/8/9/10/11/12 条。
算法本身（三个夹子、倍速、循环刷）在 test_video_watch.py，这里钉的是门控、落库、
裁决权移交与降级路径。

时间控制：心跳之间要"过去 15 秒"，但测试不能真等。做法是**直接改账本行的
last_beat_at**（把它往前拨），这与真实流逝在服务端看来完全等价——服务端算的就是
`now - last_beat_at`。
"""
from datetime import timedelta
from pathlib import Path

from test_exam import build_app, scsrf, student_login
from test_lesson_block_unlock import build_lesson_with_blocks
from test_student_learning import seed_ready_video

from app.models import LessonBlockCompletion, LessonVideoWatch
from app.security import utcnow

DURATION = 600  # 10 分钟的视频


def build_video_lesson(app, *, completion_percent=80, source_type="platform",
                       duration=DURATION, extra_blocks=(), authoritative=True,
                       unlock_rule="free"):
    """建一节含视频块的已发布课时，并把裁决权开关打开（B3 默认关，测试里要验的是开着的行为）。"""
    app.state.settings.video_watch_authoritative = authoritative
    detail = {"source_type": source_type, "completion_percent": completion_percent}
    if source_type == "platform":
        video = seed_ready_video(app)
        _set_duration(app, video["video_id"], duration)
        detail["video_id"] = video["video_id"]
    else:
        detail["video_url"] = "https://example.com/v.mp4"
    blocks = [dict(b) for b in extra_blocks]
    blocks.append({"block_type": "video", "title": "视频块",
                   "unlock_rule": unlock_rule, **detail})
    built = build_lesson_with_blocks(app, blocks)
    built["video_block_id"] = built["block_ids"][-1]
    return built


def rebind_video(app, block_id: int, new_video_id: int):
    """直接改库换绑视频。

    走管理端接口做不到——课包发布后 `_require_editable` 一律 409，而这个测试要的
    前提恰恰是「学生已经在已发布的课时上看了一段」。要验的是账本的 video_id 失配
    分支，不是后台的编辑权限，直接改库更贴题。
    """
    from sqlalchemy import select

    from app.models import LessonVideoBlock
    db = app.state.session_factory()
    try:
        vd = db.scalar(select(LessonVideoBlock).where(LessonVideoBlock.block_id == block_id))
        vd.video_id = new_video_id
        db.commit()
    finally:
        db.close()


def _set_duration(app, video_id: int, duration: int | None):
    from app.models import Video
    db = app.state.session_factory()
    try:
        db.get(Video, video_id).duration_seconds = duration
        db.commit()
    finally:
        db.close()


def watch(client, lesson_id, block_id, position):
    return client.post(
        f"/api/lessons/{lesson_id}/blocks/{block_id}/watch",
        headers=scsrf(client), json={"position_seconds": position},
    )


def complete(client, lesson_id, block_id, **body):
    return client.post(
        f"/api/lessons/{lesson_id}/blocks/{block_id}/complete",
        headers=scsrf(client), json=body or {"source": "manual"},
    )


def rewind_beat(app, block_id, seconds):
    """把账本的 last_beat_at 往前拨 seconds 秒，模拟"过去了这么久"。"""
    db = app.state.session_factory()
    try:
        row = db.scalar(
            __import__("sqlalchemy").select(LessonVideoWatch)
            .where(LessonVideoWatch.block_id == block_id)
        )
        row.last_beat_at = utcnow() - timedelta(seconds=seconds)
        db.commit()
    finally:
        db.close()


def ledger(app, block_id):
    db = app.state.session_factory()
    try:
        from sqlalchemy import select
        return db.scalar(select(LessonVideoWatch).where(LessonVideoWatch.block_id == block_id))
    finally:
        db.close()


def completions(app, block_id) -> int:
    db = app.state.session_factory()
    try:
        from sqlalchemy import select
        return len(list(db.scalars(
            select(LessonBlockCompletion).where(LessonBlockCompletion.block_id == block_id))))
    finally:
        db.close()


def play_through(client, app, lesson_id, block_id, *, step=15, upto=DURATION):
    """按 step 秒一拍匀速看到 upto，每拍之间把墙钟往前拨 step 秒。"""
    position, last = 0, None
    while position < upto:
        position = min(upto, position + step)
        last = watch(client, lesson_id, block_id, position)
        assert last.status_code == 200, last.text
        if position < upto:
            rewind_beat(app, block_id, step)
    return last


# ---------- 正常路径 ----------


def test_watching_through_completes_the_block(tmp_path: Path):
    """验收 §10-3：匀速看完整部片子 → 达标 → 写完成记录。

    注意这里放的是**整部** 600 秒，而不是刚好 480 秒的阈值线：首拍不记时长
    （没有"上一拍"就没有流逝时间可言，见 video_watch.credit），所以看到刚好
    480 秒时账上是 465 秒，差一拍。真实场景里 completion_percent 留了 20% 余量，
    这一拍的损耗被吸收掉；卡着阈值线一秒不多看的学生才会碰到，属于可接受代价。
    """
    app = build_app(tmp_path)
    built = build_video_lesson(app, completion_percent=80)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)

    body = play_through(sclient, app, lid, bid, upto=DURATION).json()
    assert body["completed"] is True
    assert body["required_seconds"] == 480
    assert body["watched_seconds"] >= 480
    assert completions(app, bid) == 1


def test_watching_exactly_to_the_threshold_is_one_beat_short(tmp_path: Path):
    """首拍不记时长的代价，如实钉住：看到刚好 80% 时账上差一拍。

    这条不是在庆祝一个缺陷，是在**防止有人"顺手修好"它**——让首拍按 position
    记账，等于把「第一拍直接报片尾」这个洞重新打开（见 test_video_watch.py
    的 test_first_beat_credits_nothing）。要缓解只能靠 completion_percent 的余量。
    """
    app = build_app(tmp_path)
    built = build_video_lesson(app, completion_percent=80)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)

    body = play_through(sclient, app, lid, bid, upto=480).json()
    assert body["watched_seconds"] == 465  # 480 - 一拍 15 秒
    assert body["completed"] is False


def test_watch_reports_progress_without_completing(tmp_path: Path):
    app = build_app(tmp_path)
    built = build_video_lesson(app, completion_percent=80)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)

    body = play_through(sclient, app, lid, bid, upto=60).json()
    assert body["completed"] is False
    assert 0 < body["watched_seconds"] < 480
    assert body["percent"] < 100
    assert completions(app, bid) == 0


def test_resume_position_is_returned(tmp_path: Path):
    """续播断点：max_position 回给前端，跨会话不丢。"""
    app = build_app(tmp_path)
    built = build_video_lesson(app)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)
    play_through(sclient, app, lid, bid, upto=120)
    assert watch(sclient, lid, bid, 120).json()["resume_position_seconds"] == 120


# ---------- 作弊路径（本方案的核心保证）----------


def test_single_beat_claiming_the_whole_video_is_rejected(tmp_path: Path):
    """验收 §10-1：一发请求直接报片尾，只能记一拍的量，绝不达标。"""
    app = build_app(tmp_path)
    built = build_video_lesson(app, completion_percent=80)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)

    body = watch(sclient, lid, bid, DURATION).json()
    assert body["completed"] is False
    assert body["watched_seconds"] == 0, "首拍不该记时长"
    assert completions(app, bid) == 0


def test_banked_wallclock_cannot_be_cashed_in_one_beat(tmp_path: Path):
    """验收 §10-2（攒时长攻击）：挂 40 分钟再拖到片尾发一拍。

    墙钟确实过去了 2400 秒，但 BEAT_CAP 把这一拍能兑现的量封在 45×2.5=112 秒。
    **这条挂了就说明 BEAT_CAP 被人删了**，方案的核心保证随之失效。
    """
    app = build_app(tmp_path)
    built = build_video_lesson(app, completion_percent=80)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)

    watch(sclient, lid, bid, 0)          # 首拍建账
    rewind_beat(app, bid, 2400)          # 挂机 40 分钟
    body = watch(sclient, lid, bid, DURATION).json()   # 拖到片尾

    assert body["completed"] is False
    assert body["watched_seconds"] <= 120, f"攒时长攻击成立：记了 {body['watched_seconds']} 秒"
    assert completions(app, bid) == 0


def test_looping_the_intro_does_not_complete(tmp_path: Path):
    """验收 §10-6：循环看前 20%，累计时长够了但最远位置没到，不算完成。"""
    app = build_app(tmp_path)
    built = build_video_lesson(app, completion_percent=80)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)

    # 5 遍 × 120 秒 ≈ 585 秒累计，已经超过 480 的阈值线。
    # 不要为了"更有说服力"把圈数加大——心跳限流是 60/分钟，圈数一多测试自己会撞 429，
    # 那是限流在起作用，不是记账在起作用，会把这条回归变成一个假阳性。
    for _ in range(5):
        play_through(sclient, app, lid, bid, upto=120)
        rewind_beat(app, bid, 15)
        watch(sclient, lid, bid, 0)   # 拖回开头
        rewind_beat(app, bid, 15)

    row = ledger(app, bid)
    assert row.watched_seconds >= 480, "前提没成立：累计时长还没超过阈值"
    assert row.max_position_seconds < 480
    assert completions(app, bid) == 0, "循环看片头不该算完成"


def test_two_tabs_do_not_double_count(tmp_path: Path):
    """验收 §10-7：两个标签页同时心跳，累计时长仍被真实墙钟夹住。

    这条钉的是「账本按 (user, block) 唯一」这个建表决策——按播放会话分行的话，
    每个标签页各拿一份完整墙钟预算，开 N 个标签页就能刷成 N 倍。
    """
    app = build_app(tmp_path)
    built = build_video_lesson(app, completion_percent=80)
    lid, bid = built["lesson_id"], built["video_block_id"]
    tab_a = student_login(app)
    tab_b = tab_a  # 同一个学生的两个标签页 = 同一套 cookie

    watch(tab_a, lid, bid, 0)
    total_wallclock = 0
    position = 0
    for _ in range(10):
        rewind_beat(app, bid, 15)
        total_wallclock += 15
        position += 15
        watch(tab_a, lid, bid, position)
        # 第二个标签页紧跟着报同一时刻的位置，中间没有额外墙钟流逝
        watch(tab_b, lid, bid, position)

    row = ledger(app, bid)
    assert row.watched_seconds <= total_wallclock * 2.5 + 1, (
        f"两个标签页把时长刷成了 {row.watched_seconds}，墙钟只有 {total_wallclock}")


# ---------- 门控 ----------


def test_locked_block_cannot_be_credited(tmp_path: Path):
    """验收 §10-8：顺序锁住的视频块上发心跳 → 403，且不写账本。

    少了这道闸，学生能隔着锁把时长刷满，等块一解锁当场达标，闯关闸等于没有。
    """
    app = build_app(tmp_path)
    # 视频块排在图文之后并要求顺序解锁：前置图文没完成，视频块就是 sequential 锁
    built = build_video_lesson(
        app, unlock_rule="sequential",
        extra_blocks=[{"block_type": "markdown", "title": "前置"}])
    lid, bid = built["lesson_id"], built["video_block_id"]

    sclient = student_login(app)
    r = watch(sclient, lid, bid, 15)
    assert r.status_code == 403
    assert ledger(app, bid) is None, "锁定块不该留下账本行"


# ---------- 裁决权移交与降级 ----------


def test_client_completion_is_ignored_for_adjudicated_blocks(tmp_path: Path):
    """验收 §10-9：账本模式下，客户端 POST /complete 对视频块不再有写入能力。"""
    app = build_app(tmp_path)
    built = build_video_lesson(app, completion_percent=80, authoritative=True)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)

    r = complete(sclient, lid, bid, source="video", progress_percent=100)
    assert r.status_code == 200, "老前端还在打这个端点，不该报错"
    assert r.json()["completed"] is False
    assert completions(app, bid) == 0, "客户端上报把块刷成了完成——裁决权没移交干净"


def test_embed_block_falls_back_to_manual(tmp_path: Path):
    """验收 §10-10：embed 拿不到播放位置，维持手动确认即完成。

    不能为了口径统一把它一起卡住——那会让所有用 B 站外链的课时集体无法完成。
    """
    app = build_app(tmp_path)
    built = build_video_lesson(app, source_type="embed", completion_percent=80,
                               authoritative=True)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)

    r = complete(sclient, lid, bid, source="video", progress_percent=100)
    assert r.status_code == 200 and r.json()["completed"] is True
    assert completions(app, bid) == 1


def test_platform_without_duration_falls_back_to_manual(tmp_path: Path):
    """验收 §10-11：转码元数据异常（时长为空）→ 降级，不能拿运维问题卡学生。"""
    app = build_app(tmp_path)
    built = build_video_lesson(app, completion_percent=80, duration=None,
                               authoritative=True)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)

    assert watch(sclient, lid, bid, 100).json()["completion_mode"] == "manual"
    r = complete(sclient, lid, bid, source="video", progress_percent=100)
    assert r.status_code == 200 and r.json()["completed"] is True


def test_rebinding_the_video_resets_the_ledger(tmp_path: Path):
    """验收 §10-12：换绑视频后旧账作废，否则能拿旧视频的时长兑现新视频的完成度。"""
    app = build_app(tmp_path)
    built = build_video_lesson(app, completion_percent=80)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)
    play_through(sclient, app, lid, bid, upto=300)
    assert ledger(app, bid).watched_seconds >= 280

    other = seed_ready_video(app, title="换一个")
    _set_duration(app, other["video_id"], DURATION)
    rebind_video(app, bid, other["video_id"])

    watch(sclient, lid, bid, 30)
    row = ledger(app, bid)
    assert row.video_id == other["video_id"]
    assert row.watched_seconds == 0, "换绑后旧账没清，学生能拿旧时长兑现新视频"


def test_grace_period_keeps_client_reporting(tmp_path: Path):
    """灰度期（VIDEO_WATCH_AUTHORITATIVE=false）：老前端的阈值上报仍然有效。

    B2 前端没全量之前就把开关打开，学生的视频块会全部完不成——这条钉住灰度姿态。
    """
    app = build_app(tmp_path)
    built = build_video_lesson(app, completion_percent=80, authoritative=False)
    lid, bid = built["lesson_id"], built["video_block_id"]
    sclient = student_login(app)

    assert complete(sclient, lid, bid, source="video",
                    progress_percent=100).json()["completed"] is True
    assert completions(app, bid) == 1
    # 但阈值仍然按 block_type 判，不是按 source 判（上一轮修的那个洞不能退回去）
    app2 = build_app(tmp_path / "b")
    b2 = build_video_lesson(app2, completion_percent=80, authoritative=False)
    s2 = student_login(app2)
    r = complete(s2, b2["lesson_id"], b2["video_block_id"], source="manual", progress_percent=0)
    assert r.json()["completed"] is False
