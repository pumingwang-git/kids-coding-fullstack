"""视频观看时长记账：把「看了多久」从客户端断言变成服务端事实。

见《20、视频观看时长服务端记账-设计-2026-08-13》。改本文件前先读设计文档 §1.1 与 §4。

## 这个模块保证什么，不保证什么

**不是防作弊，是给作弊标价。** 落地前，`progress_percent: 100` 一个请求就能刷完
任何视频；落地后，要刷满一个 D 秒的视频至少得挂 `D / TOLERANCE` 秒真实墙钟时间。

**它挡不住挂机。** 服务端没有任何办法区分「开着页面不看」与「看了但没互动」——
要连挂机一起管住只能上随堂弹题，那是产品形态改动，不在本模块职责内。
写在这里是为了让下一个读代码的人不要以为漏了什么。

## 为什么不数切片

最直觉的做法是数学生取了多少个 .ts。**本项目的部署形态下这条路是堵死的**：
部署配置/nginx-cache.conf 里切片由 nginx 用 secure_link 校验后直连 MinIO
（`proxy_pass http://127.0.0.1:9000`），**应用完全看不见切片流量**——那正是
app/video_sign.py 那套边缘鉴权的全部意义。把切片拉回应用等于让整套加速方案作废。
所以只剩「客户端心跳 + 服务端墙钟下界」这一条路。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .security import as_utc

# 一个视频块的完成度由谁裁决。**前端只认这个字段**，不要在客户端按 source_type
# 重新推一遍——推错的后果是学生卡在一个永远完不成的块上。
LEDGER = "ledger"   # 服务端账本裁决：客户端的完成上报无效
MANUAL = "manual"   # 降级：服务端无从裁决，学生手动确认即完成


def completion_mode(video_block, video) -> str:
    """这个视频块的完成度能不能由服务端裁决。

    **只有 platform（平台转码视频）且时长已知才能进账本裁决**，理由是「服务端必须
    同时拿得到播放位置和视频总时长」，缺一个都算不出阈值：

    - ``embed``（第三方 iframe）：位置、时长都拿不到。`completion_percent` 对它
      **从来就没生效过**，本方案也给不了——不要为了"口径统一"把它一起卡住，
      那会让所有用 B 站外链的课时集体无法完成（设计文档 §9.5）。
    - ``direct``（外链 MP4/HLS）：播放器**报得出位置**，但服务端没有 Video 行、
      因而**不知道总时长**（admin_course_content.py 建块时 direct 的 video_id 恒为
      None）。没有分母就没有阈值。
      *不要改成"信客户端报的时长"*：报一个 duration=1 就能让阈值变成 1 秒，
      等于把刚堵上的洞换个地方重新开一遍。
    - ``platform`` 但 ``duration_seconds`` 为空：转码元数据异常。此时卡住学生是
      让他承担运维问题，一律降级（设计文档 §9.4）。

    降级块沿用旧行为（手动确认即完成），这是有意的：它们本来就没有比这更强的保证。
    """
    if video_block is None or video_block.source_type != "platform":
        return MANUAL
    if video is None or not video.duration_seconds or video.duration_seconds <= 0:
        return MANUAL
    return LEDGER


@dataclass(frozen=True)
class Credit:
    """一次心跳的记账结果。"""

    credited: int          # 本次认可的秒数
    watched_seconds: int   # 记账后的累计观看秒数
    max_position: int      # 记账后到达过的最远位置


def credit(
    *,
    position_seconds: int,
    duration_seconds: int | None,
    prev_position: int,
    prev_watched: int,
    prev_max_position: int,
    last_beat_at: datetime | None,
    now: datetime,
    beat_cap_seconds: int,
    tolerance: float,
) -> Credit:
    """算一次心跳该认可多少观看时长。**纯函数，不碰数据库**（照 scoring.py 的规矩）。

    核心就一行：

        credited = clamp(position_delta, 0, min(wallclock_delta, BEAT_CAP) × TOLERANCE)

    三个夹子各挡一类作弊，**少一个漏一类**：

    1. `position_delta` —— 不放视频（位置不动）就不记账，挡「开着页面挂机涨进度」；
    2. `wallclock_delta` —— 一次拖到片尾也只能记这段真实流逝的时间，挡「拖到底一次上报」；
    3. `beat_cap_seconds` —— **最容易被当成优化删掉的那个，别删**。它挡的是「攒时长」：
       打开页面干等 40 分钟、把位置拖到片尾、发一次心跳。此时 wallclock_delta=2400s、
       position_delta=2400s，没有这个上限就是**一次请求兑现整部视频**，墙钟下界白设。
       有了它（建议 45s = 3×心跳间隔），这一拍最多记 45×2.5≈112s，要刷满 40 分钟的视频
       必须真发 ~21 次心跳、真等 ~16 分钟。

    tolerance 覆盖倍速播放：2.5 放行到 2x（2x 时 position_delta=2×wallclock，仍在预算内），
    3x 播完账上只有 ~83%。**调高它就是等比例调低作弊成本**——调到 4 就支持 4x 倍速，
    同时作弊只需时长的 1/4。改这个数前先读设计文档 §9.1。

    后拖（回看）时 position_delta 为负，`max(0, …)` 记 0 而**不扣**已有时长：
    回看是正常学习行为，扣时长会逼学生不敢复习。
    """
    # 位置先钳进 [0, duration]：客户端报个 10^9 不能把账本冲垮。
    # duration 未知时不设上界（该视频走降级路径，见 completed()）。
    position = max(0, int(position_seconds))
    if duration_seconds and duration_seconds > 0:
        position = min(position, duration_seconds)

    if last_beat_at is None:
        # 本次是这一行的第一拍：没有上一拍就没有"流逝了多久"可言，
        # 只登记位置不记时长。少记一拍（≤15s）换掉「首拍直接报片尾」这个口子。
        return Credit(0, prev_watched, max(prev_max_position, position))

    wallclock_delta = (as_utc(now) - as_utc(last_beat_at)).total_seconds()
    position_delta = position - prev_position
    budget = min(max(wallclock_delta, 0.0), beat_cap_seconds) * tolerance
    credited = int(max(0.0, min(float(position_delta), budget)))

    return Credit(
        credited=credited,
        watched_seconds=prev_watched + credited,
        max_position=max(prev_max_position, position),
    )


def required_seconds(duration_seconds: int | None, completion_percent: int) -> int | None:
    """达标线（秒）。duration 未知时返回 None —— 调用方必须走降级路径。"""
    if not duration_seconds or duration_seconds <= 0:
        return None
    percent = min(100, max(0, completion_percent))
    return int(duration_seconds * percent / 100)


def completed(watched_seconds: int, max_position_seconds: int,
              required: int | None) -> bool:
    """达标判定：累计时长与最远位置**两个条件都要满足**。

    只看 watched_seconds 的话，把前 20% 循环放五遍就能凑够时长。加上
    max_position_seconds 几乎零成本地堵掉了循环刷，代价是「只看后半段」的学生
    也判未达标——这符合 completion_percent「看到第 N%」的语义。

    更精确的做法是存观看区间集合按并集长度判，能回答「哪几段没看」，但要处理
    区间合并、行膨胀与并发写。本期用这个近似，将来升级时 watched_seconds
    可由区间集合推导，账本不用重建（设计文档 §4.4）。
    """
    if required is None:
        return False  # 时长未知：判定权交给降级路径，不在这里放行
    return watched_seconds >= required and max_position_seconds >= required
