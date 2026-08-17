"""异步判题的执行器：一个有界线程池 + 一条看得见的队列。

为什么要异步（2026-08-07 算过的账）：
判题是同步阻塞的时候，一次提交会**全程占着一个 DB 连接**（run_code 里 flush 开了事务，
判完才 commit）。连接池是 5+10=15，于是只要 15 个人同时在判题，整个后端所有接口都
拿不到连接——包括「保存答案」和「交卷」。考场里最不能丢的恰恰是自动保存，而症状会是
"我的答案存不上了"，跟判题看着毫无关系，极难排查。

改成异步之后：请求线程只负责落一条 queued 记录就返回，判题在这个池子里跑，
worker 自己开 session 且**在判题期间不持有连接**（判前 commit 一次、判完再开）。

这个池子顺带就是全局判题并发闸。池子大小 ≈ 2× go-judge 的 -parallelism，
理由见 config.judge_workers 的注释——它不决定吞吐，只决定队列排在哪儿。

进程重启会丢掉在途任务，这是选进程内线程池的已知代价。靠 sweep_stale_judgings
兜底：卡太久的置 judge_failed，成绩留 null 而不是 0。
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def judge_key(kind: str, item_id: int) -> str:
    """队列键。**不能只用自增 id**：队列里同时排着学员提交（code_submissions）和
    管理端的参考代码试跑（problem_dry_runs），两张表的 id 各自从 1 开始，必然会撞。
    撞了的表现是一条任务把另一条从队列里挤掉——位次乱报，且极难复现。"""
    return f"{kind}:{item_id}"


@dataclass(frozen=True)
class JudgeTask:
    """一次待判的任务。

    custom_input 只活在内存里、不落库：它是自测用的一次性 stdin，没有留档价值，
    而且进程重启后这条任务本来就会被 sweep 成 judge_failed，存了也用不上。

    kind 决定这条任务由谁执行（见 main.py 的分发）以及队列键的前缀：
    "submission" = 学员的代码提交，"dry_run" = 管理端的参考代码试跑。
    """

    submission_id: int
    custom_input: str | None = None
    kind: str = "submission"

    @property
    def key(self) -> str:
        return judge_key(self.kind, self.submission_id)


class JudgeQueueFull(RuntimeError):
    """排队已满。调用方应转成 429，而不是让请求挂在那里等。"""


class JudgeRunner:
    """把判题任务丢进有界线程池，并对外报告排队位次。"""

    def __init__(self, worker, *, workers: int, queue_max: int):
        self._worker = worker
        self._queue_max = queue_max
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="judge")
        self._lock = threading.Lock()
        # 有序字典当队列用：既要报"前面还有几个"，又要能 O(1) 删除已开跑的。
        # 键是 judge_key() 生成的 "kind:id" 字符串，不是裸 id，理由见该函数。
        self._waiting: OrderedDict[str, None] = OrderedDict()
        self._running: set[str] = set()

    # ---------- 对外 ----------

    def enqueue(self, task: JudgeTask) -> int:
        """入队并返回身前还有多少个在等。在途总数超上限时抛 JudgeQueueFull。

        上限算的是**排队中 + 正在跑**的总数，不是只算排队中。只算排队的话，
        线程池刚把任务领走队列就空了，上限形同虚设——真正要防的是"在途总量失控"。
        """
        with self._lock:
            if len(self._waiting) + len(self._running) >= self._queue_max:
                raise JudgeQueueFull(f"判题在途已满（{self._queue_max}）")
            ahead = len(self._waiting)
            self._waiting[task.key] = None
        self._pool.submit(self._run, task)
        return ahead

    def position(self, key: str) -> int | None:
        """身前还有几个在排队。已经开跑返回 0，不在队里返回 None。

        参数是 judge_key() 生成的键，不是裸 id——调用方用 judge_key("submission", x)。
        """
        with self._lock:
            if key in self._running:
                return 0
            if key not in self._waiting:
                return None
            for index, waiting_key in enumerate(self._waiting):
                if waiting_key == key:
                    return index
        return None

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"waiting": len(self._waiting), "running": len(self._running)}

    def shutdown(self, wait: bool = False) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=True)

    # ---------- 内部 ----------

    def _run(self, task: JudgeTask) -> None:
        with self._lock:
            self._waiting.pop(task.key, None)
            self._running.add(task.key)
        try:
            self._worker(task)
        except Exception:
            # 线程池里抛出去的异常没人接，会变成静默丢失的提交。这里兜住并留痕；
            # worker 内部已经把 judge_failed 落库了，这条日志是给运维看的。
            logger.exception("判题任务异常退出：submission_id=%s", task.submission_id)
        finally:
            with self._lock:
                self._running.discard(task.key)
