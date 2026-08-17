"""观看时长记账的纯函数回归（app/video_watch.py）。

《20、视频观看时长服务端记账-设计-2026-08-13》§10 验收清单第 1/2/4/5/6 条。

这个文件钉的是**方案的核心保证**：一次心跳能记多少时长，由三个夹子共同决定，
少任何一个就漏一类作弊。端到端的门控与落库在 test_lesson_video_watch.py。
"""
from datetime import UTC, datetime, timedelta

from app.video_watch import LEDGER, MANUAL, completed, completion_mode, credit, required_seconds

BEAT_CAP = 45
TOLERANCE = 2.5
T0 = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


def beat(*, position, prev_position=0, prev_watched=0, prev_max=0,
         last_beat_at=T0, now=None, elapsed=15):
    """跑一拍。默认「上一拍在 T0，本拍在 T0+15s」。"""
    return credit(
        position_seconds=position,
        duration_seconds=2400,  # 40 分钟
        prev_position=prev_position,
        prev_watched=prev_watched,
        prev_max_position=prev_max,
        last_beat_at=last_beat_at,
        now=now or (T0 + timedelta(seconds=elapsed)),
        beat_cap_seconds=BEAT_CAP,
        tolerance=TOLERANCE,
    )


# ---------- 正常观看 ----------


def test_normal_playback_credits_the_elapsed_position():
    """匀速看 15 秒就记 15 秒。"""
    assert beat(position=15, prev_position=0).credited == 15


def test_watched_seconds_accumulates():
    result = beat(position=30, prev_position=15, prev_watched=15)
    assert result.watched_seconds == 30 and result.max_position == 30


# ---------- 三个夹子 ----------


def test_paused_player_credits_nothing():
    """夹子一：位置不动 = 没在放，挂机不记账。"""
    assert beat(position=15, prev_position=15).credited == 0


def test_seek_to_end_is_clamped_by_wallclock():
    """夹子二：一拍之内拖到片尾，只能记这 15 秒真实流逝的时间（×容差）。"""
    result = beat(position=2400, prev_position=0, elapsed=15)
    assert result.credited == int(15 * TOLERANCE) == 37


def test_banked_wallclock_cannot_be_cashed_in_one_beat():
    """夹子三（**设计文档 §4.3 攒时长攻击**）：干等 40 分钟再拖到片尾发一拍。

    没有 BEAT_CAP 的话这一拍能记满 2400 秒——一次请求兑现整部视频，墙钟下界白设。
    有了它，这一拍最多记 45×2.5=112 秒。
    """
    result = beat(position=2400, prev_position=0, elapsed=2400)
    assert result.credited == int(BEAT_CAP * TOLERANCE) == 112
    assert result.credited < 2400


def test_first_beat_credits_nothing():
    """首拍没有"上一拍"就没有流逝时间可言，只登记位置。

    少了这条，第一拍直接报片尾就能白拿一整段（last_beat_at 为空时 wallclock 无从算起）。
    """
    result = credit(
        position_seconds=2400, duration_seconds=2400, prev_position=0, prev_watched=0,
        prev_max_position=0, last_beat_at=None, now=T0,
        beat_cap_seconds=BEAT_CAP, tolerance=TOLERANCE,
    )
    assert result.credited == 0 and result.watched_seconds == 0
    assert result.max_position == 2400  # 位置照记，续播要用


# ---------- 倍速 ----------


def test_two_x_playback_is_fully_credited():
    """2x：15 秒墙钟推进 30 秒位置，容差 2.5 之内，全额记账。"""
    assert beat(position=30, prev_position=0, elapsed=15).credited == 30


def test_three_x_playback_is_partially_credited():
    """3x：超出容差的部分不记。整部片子看完账上只有约 83%。"""
    assert beat(position=45, prev_position=0, elapsed=15).credited == 37


def test_three_x_full_run_lands_around_83_percent():
    """3x 从头到尾跑完 2400 秒的片子，累计记账 ≈ 2400 × 2.5/3。"""
    watched, position, now = 0, 0, T0
    while position < 2400:
        nxt = min(2400, position + 45)  # 每 15 秒墙钟推进 45 秒位置
        result = credit(
            position_seconds=nxt, duration_seconds=2400, prev_position=position,
            prev_watched=watched, prev_max_position=position, last_beat_at=now,
            now=now + timedelta(seconds=15), beat_cap_seconds=BEAT_CAP, tolerance=TOLERANCE,
        )
        watched, position, now = result.watched_seconds, nxt, now + timedelta(seconds=15)
    assert 1950 <= watched <= 2050, watched  # ≈ 2400 × 5/6
    assert not completed(watched, position, required_seconds(2400, 100))


# ---------- 拖动 ----------


def test_rewind_never_subtracts():
    """后拖（回看）记 0，但**不扣**已有时长——扣分会逼学生不敢复习。"""
    result = beat(position=100, prev_position=500, prev_watched=500, prev_max=500)
    assert result.credited == 0
    assert result.watched_seconds == 500 and result.max_position == 500


def test_position_beyond_duration_is_clamped():
    """客户端报个超长位置不能把账本冲垮。"""
    result = beat(position=10**9, prev_position=0, elapsed=15)
    assert result.max_position == 2400


# ---------- 达标判定 ----------


def test_completion_needs_both_time_and_reach():
    required = required_seconds(2400, 80)  # 1920
    assert required == 1920
    assert completed(1920, 1920, required)
    assert not completed(1919, 2400, required)   # 时长不够
    assert not completed(2400, 1919, required)   # 位置没到


def test_looping_the_intro_does_not_complete():
    """把前 20% 循环放五遍：累计时长够了，但最远位置没到，不算完成（§4.4）。"""
    required = required_seconds(2400, 80)
    assert not completed(watched_seconds=2400, max_position_seconds=480, required=required)


def test_unknown_duration_never_completes_here():
    """时长未知时本函数一律不放行，判定权交给降级路径（§9.4）。"""
    assert required_seconds(None, 80) is None
    assert not completed(99999, 99999, None)


# ---------- 裁决模式 ----------


class _VB:
    def __init__(self, source_type):
        self.source_type = source_type


class _V:
    def __init__(self, duration_seconds):
        self.duration_seconds = duration_seconds


def test_only_platform_with_duration_is_adjudicated():
    assert completion_mode(_VB("platform"), _V(2400)) == LEDGER
    # embed 拿不到位置；direct 拿得到位置但服务端没有时长（video_id 恒为 None）
    assert completion_mode(_VB("embed"), None) == MANUAL
    assert completion_mode(_VB("direct"), None) == MANUAL
    # platform 但转码元数据异常：降级，不能拿运维问题卡学生
    assert completion_mode(_VB("platform"), _V(None)) == MANUAL
    assert completion_mode(_VB("platform"), _V(0)) == MANUAL
    assert completion_mode(None, None) == MANUAL
