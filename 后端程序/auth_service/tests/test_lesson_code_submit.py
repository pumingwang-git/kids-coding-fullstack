"""课时内编程题**计分提交**回归（文档 18 §3.1 方案③）。

与 test_lesson_code_run.py 的分工：那边是「只运行不计分」（scope=samples/custom），
这边是「跑全部测试点并计分」（scope=all）。分文件是因为两条链路的红线不同——

**本文件最重要的一条**：计分提交必须跑隐藏测试点，但隐藏点的输入/期望/实际
一个字都不能下发。scope=samples 时之所以安全，只是因为压根没取隐藏点；
加了 scope=all 之后，裁剪就成了唯一的防线。
"""
import time
from pathlib import Path

from test_exam import build_app, scsrf, student_login
from test_lesson_block_unlock import build_lesson_with_blocks
from test_lesson_code_run import (
    SECRET_INPUT,
    SECRET_OUTPUT,
    build_coding_lesson,
    get_problem,
    seed_programming_problem,
    start_run,
)

from app.models import (
    LessonBlockCompletion,
    LessonCodeRun,
    LessonProblemAttempt,
    Problem,
    ProgrammingDetail,
)


def set_pass_condition(app, problem_id_no: str, condition: str):
    """把满分条件钉死。

    ProgrammingDetail.pass_condition 的**模型默认值是「编译通过」**，
    所以不显式设置的话，seed 出来的题全是编译通过型——那种题编译过了就满分，
    测不出"测试点没过该判 0 分"。这条踩过一次，写在这里省下下一个人半小时。
    """
    db = app.state.session_factory()
    try:
        problem = db.query(Problem).filter_by(problem_id_no=problem_id_no).one()
        detail = db.get(ProgrammingDetail, problem.id)
        detail.pass_condition = condition
        db.commit()
    finally:
        db.close()


def submit(sclient, lid, bid, **body):
    payload = {"language": "cpp", "code": "cout<<1;", **body}
    return sclient.post(f"/api/lessons/{lid}/blocks/{bid}/submit",
                        headers=scsrf(sclient), json=payload)


# 判题走**进程内线程池**（见 app/judge/runner.py 头注），submit 返回 201 时结果
# 多半还没落库。因此必须轮询到终态：满载全量里线程池被上千条用例抢，单次 GET
# 会读到 judging，表现为 `assert 'judging' == 'judge_failed'` 这类与判题逻辑
# 毫无关系的假红（2026-08-26 收口全量实测命中）。
_TERMINAL_RUN_STATUSES = frozenset({
    "accepted", "wrong_answer", "compile_error",
    "runtime_error", "time_limit", "memory_limit", "judge_failed",
})


def poll(sclient, lid, bid, run_id, *, timeout: float = 15.0):
    """轮询到终态或超时后返回最后一次响应。

    **不要改成定长 sleep**：空载白等，满载又不够。超时也照常返回最后那次响应，
    让调用方的断言自己报错——错误信息里能看到它停在 judging，比这里抛超时好定位。
    """
    deadline = time.monotonic() + timeout
    while True:
        response = sclient.get(f"/api/lessons/{lid}/blocks/{bid}/runs/{run_id}")
        if response.status_code != 200:
            return response
        if response.json().get("status") in _TERMINAL_RUN_STATUSES:
            return response
        if time.monotonic() >= deadline:
            return response
        time.sleep(0.05)


def reset(sclient, lid, bid):
    return sclient.post(f"/api/lessons/{lid}/blocks/{bid}/reset", headers=scsrf(sclient))


# ---------- Python 作品题暂未接入普通判题链 ----------


def mark_project_shape(app, problem_id_no):
    db = app.state.session_factory()
    try:
        problem = db.query(Problem).filter_by(problem_id_no=problem_id_no).one()
        db.get(ProgrammingDetail, problem.id).shape = "project"
        db.commit()
    finally:
        db.close()


def test_project_shape_run_is_rejected_without_creating_run(tmp_path: Path):
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    mark_project_shape(app, no)
    sclient = student_login(app)

    response = start_run(sclient, built["lesson_id"], built["block_ids"][-1],
                         code="print('project')")
    assert response.status_code == 409
    assert response.json()["detail"] == "作品题提交暂未开放。"

    db = app.state.session_factory()
    try:
        assert db.query(LessonCodeRun).count() == 0
        assert db.query(LessonBlockCompletion).count() == 0
    finally:
        db.close()


def test_project_shape_submit_is_rejected_without_consuming_attempt(tmp_path: Path):
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    mark_project_shape(app, no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    response = submit(sclient, lid, bid, code="print('project')")
    assert response.status_code == 409
    assert response.json()["detail"] == "作品题提交暂未开放。"
    assert get_problem(sclient, lid, bid).json()["tries"] == 0

    db = app.state.session_factory()
    try:
        assert db.query(LessonCodeRun).count() == 0
        assert db.query(LessonBlockCompletion).count() == 0
    finally:
        db.close()


# ---------- 保密红线 ----------


def test_submit_runs_hidden_cases_but_never_reveals_them(tmp_path: Path):
    """跑隐藏点，但只回状态与耗时；输入/期望/实际一律 null，库里也不许留。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    started = submit(sclient, lid, bid)
    assert started.status_code == 201, started.text
    polled = poll(sclient, lid, bid, started.json()["run_id"])
    body = polled.json()

    assert body["done"] is True and body["scored"] is True
    assert len(body["cases"]) == 2, "计分提交要跑全部测试点（1 样例 + 1 隐藏）"
    sample, hidden = body["cases"][0], body["cases"][1]
    assert sample["is_sample"] is True and sample["expected"] == "3\n"
    assert hidden["is_sample"] is False
    assert hidden["input"] is None and hidden["expected"] is None and hidden["actual"] is None
    assert hidden["status"], "状态照给，只是不给内容"

    assert SECRET_INPUT not in polled.text and SECRET_OUTPUT not in polled.text
    db = app.state.session_factory()
    try:
        run = db.query(LessonCodeRun).one()
        assert run.scope == "all"
        assert SECRET_INPUT not in (run.detail_json or "")
        assert SECRET_OUTPUT not in (run.detail_json or "")
    finally:
        db.close()


# ---------- 成绩与完成度 ----------


def test_submit_scores_and_completes_the_block(tmp_path: Path):
    """提交即完成：写成绩、写完成记录、解锁后面的顺序锁块。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_lesson_with_blocks(app, [
        {"block_type": "practice", "title": "编程练习",
         "problem_id_no": no, "score": 20, "display_no": "1"},
        {"title": "后续图文", "unlock_rule": "sequential"},
    ])
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][0]

    started = submit(sclient, lid, bid, code="cout<<1;")
    body = poll(sclient, lid, bid, started.json()["run_id"]).json()
    assert body["status"] == "accepted" and body["score"] == 20 and body["is_correct"] is True

    db = app.state.session_factory()
    try:
        attempt = db.query(LessonProblemAttempt).one()
        assert attempt.tries == 1 and attempt.last_score == 20
        assert db.query(LessonBlockCompletion).filter_by(block_id=bid).count() == 1
    finally:
        db.close()

    blocks = sclient.get(f"/api/lessons/{lid}").json()["blocks"]
    assert blocks[0]["completed"] is True
    assert blocks[1]["lock_reason"] is None, "提交后后续块应解锁"


def test_wrong_submission_still_completes_but_scores_zero(tmp_path: Path):
    """答错也算完成——按对错才算完成，会让学生卡在一道题上过不去。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    set_pass_condition(app, no, "全测试点通过")
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    # __WA__ 让 fake 判题器从第 2 个点开始判错（第 2 个点正是隐藏点）
    started = submit(sclient, lid, bid, code="cout<<1;//__WA__")
    body = poll(sclient, lid, bid, started.json()["run_id"]).json()
    assert body["status"] == "wrong_answer" and body["score"] == 0

    db = app.state.session_factory()
    try:
        assert db.query(LessonProblemAttempt).one().last_correct is False
        assert db.query(LessonBlockCompletion).filter_by(block_id=bid).count() == 1
    finally:
        db.close()


def test_compile_only_problem_scores_full_on_wrong_answer(tmp_path: Path):
    """满分条件是「编译通过」的题：测试点没过照样满分。

    这类题的 status 仍然是判题器给的 wrong_answer（测试点确实没过），照搬 status
    去判分就会出现「编译过了却judge成 0 分」，与题面写的满分条件自相矛盾。
    口径与前端 verdict.isCompileOnly、exam.py 的 compile_only 必须一致。
    """
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    set_pass_condition(app, no, "编译通过")
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    started = submit(sclient, lid, bid, code="cout<<1;//__WA__")
    body = poll(sclient, lid, bid, started.json()["run_id"]).json()
    assert body["status"] == "wrong_answer"
    assert body["score"] == 20 and body["is_correct"] is True


def test_judge_failure_is_not_scored_as_zero(tmp_path: Path):
    """判题挂了不是答错：不写成绩、不写完成度。那是系统的问题，不是学生的。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)

    class BrokenJudge:
        def judge(self, **_kwargs):
            from app.judge import JudgeUnavailable
            raise JudgeUnavailable("sandbox down")

    app.state.judge = BrokenJudge()
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    started = submit(sclient, lid, bid)
    body = poll(sclient, lid, bid, started.json()["run_id"]).json()
    assert body["status"] == "judge_failed" and body["done"] is True
    assert body.get("score") is None

    db = app.state.session_factory()
    try:
        assert db.query(LessonProblemAttempt).one().last_score is None
        assert db.query(LessonBlockCompletion).filter_by(block_id=bid).count() == 0
    finally:
        db.close()


# ---------- 判题失败退次数（0048） ----------
#
# 口径：次数管的是「判分几次」，不是「点击几次」。判题没出结果 = 这次不算。
# 反过来的那半边（学生代码导致的 compile_error / wrong_answer 照常计次）
# 由 test_submit_consumes_tries_and_refuses_when_exhausted 守着。


def build_limited_coding_lesson(app, *, problem_id_no, attempt_limit=1):
    return build_lesson_with_blocks(app, [{
        "block_type": "practice", "title": "编程练习", "problem_id_no": problem_id_no,
        "score": 20, "display_no": "1", "attempt_limit": attempt_limit,
    }])


class BrokenJudge:
    def judge(self, **_kwargs):
        from app.judge import JudgeUnavailable
        raise JudgeUnavailable("sandbox down")


def test_judge_failure_refunds_the_try(tmp_path: Path):
    """沙箱挂了不能吃掉学生的次数——他还能重新提交这道题。

    这是本次改动最核心的一条：改之前 attempt_limit=1 的题遇上一次判题故障，
    学生就此锁死——既交不上去（409），也没有成绩，管理员事后也查不出发生过什么。
    """
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_limited_coding_lesson(app, problem_id_no=no, attempt_limit=1)
    app.state.judge = BrokenJudge()
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    started = submit(sclient, lid, bid)
    assert started.status_code == 201
    body = poll(sclient, lid, bid, started.json()["run_id"]).json()
    assert body["status"] == "judge_failed"
    assert "不计次" in body["compile_message"], "得让学生看见这次不算，别让他自己猜"

    state = get_problem(sclient, lid, bid).json()
    assert state["tries"] == 0 and state["tries_left"] == 1, "判题没出结果就不该计次"
    assert state["can_answer"] is True
    # 次数退回去了，"已提交"的假象也跟着消失——submitted 认的是 tries 与作答同时在
    assert state["submitted"] is False

    db = app.state.session_factory()
    try:
        assert db.query(LessonCodeRun).one().charged is False, "凭据要销掉，不能重复退"
    finally:
        db.close()

    # 真正的证明：这道 attempt_limit=1 的题，学生还能再交一次
    assert submit(sclient, lid, bid).status_code == 201


def test_queue_full_refunds_the_try(tmp_path: Path):
    """排队满了是 429，次数也要退——挤不进队列的人一行代码都没被跑过。

    这条比沙箱故障更要紧：队列满是**批量**发生的，开课时段一道热门编程题
    就能让当时提交的一批人同时中招。
    """
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_limited_coding_lesson(app, problem_id_no=no, attempt_limit=1)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    def always_full(_task):
        from app.judge.runner import JudgeQueueFull
        raise JudgeQueueFull("queue is full")

    app.state.judge_runner.enqueue = always_full
    resp = submit(sclient, lid, bid)
    assert resp.status_code == 429
    assert "不计次" in resp.json()["detail"]

    state = get_problem(sclient, lid, bid).json()
    assert state["tries"] == 0 and state["can_answer"] is True


def test_refund_is_idempotent_per_run(tmp_path: Path):
    """同一条 run 走到两次失败收尾也只退一次——charged 既是凭据也是闸。

    真实触发路径：判题线程内部先把 run 标了 judge_failed，随后又抛异常落到
    _fail_run 兜底。退两次的话次数就会凭空多出来，成了刷次数的口子。
    """
    from app.routers.lesson_practice import _fail_run

    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_limited_coding_lesson(app, problem_id_no=no, attempt_limit=3)
    app.state.judge = BrokenJudge()
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    started = submit(sclient, lid, bid)
    poll(sclient, lid, bid, started.json()["run_id"])  # 判失败，已退过一次
    assert get_problem(sclient, lid, bid).json()["tries"] == 0

    db = app.state.session_factory()
    try:
        run = db.query(LessonCodeRun).one()
        run.status = "queued"  # 骗过 TERMINAL_STATUSES 的短路，强行再收尾一次
        db.commit()
        _fail_run(db, run.id, "再来一次")
    finally:
        db.close()

    assert get_problem(sclient, lid, bid).json()["tries"] == 0, "退第二次就成了刷次数的口子"


def test_migration_0048_adds_charged_defaulting_to_false(tmp_path: Path):
    """存量 run 一律 charged=false，且 downgrade 能把列拿掉。

    存量为什么不追溯退还：历史失败提交是在旧口径下扣的次数，事后既没有凭据判断
    该退给谁（run 与那次 tries+1 的对应关系当时没记），也会让已结课的成绩单对不上账。
    这条把「存量不动」钉死，免得后来人好心加一句 UPDATE。
    """
    import importlib.util

    from sqlalchemy import create_engine

    path = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
            / "0048_lesson_code_run_charged.py")
    spec = importlib.util.spec_from_file_location("m0048_charged", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def run_inline(conn, fn):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            fn()

    engine = create_engine(f"sqlite:///{tmp_path / 'migration_0048.db'}")
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("""CREATE TABLE lesson_code_runs (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, block_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL, language VARCHAR(16), scope VARCHAR(8),
                code TEXT, status VARCHAR(24), compile_message TEXT, detail_json TEXT,
                time_ms INTEGER, memory_kb INTEGER, created_at TIMESTAMP
            )""")
            conn.exec_driver_sql(
                "INSERT INTO lesson_code_runs (id, user_id, block_id, lesson_id, scope, status) "
                "VALUES (1, 1, 1, 1, 'all', 'judge_failed'), (2, 1, 1, 1, 'samples', 'accepted')"
            )
            run_inline(conn, module.upgrade)

        with engine.connect() as conn:
            cols = {row[1] for row in conn.exec_driver_sql(
                "PRAGMA table_info(lesson_code_runs)").all()}
            assert "charged" in cols
            charged = conn.exec_driver_sql(
                "SELECT id, charged FROM lesson_code_runs ORDER BY id").all()
            assert charged == [(1, 0), (2, 0)], "存量一律 false，不追溯退还"

        with engine.begin() as conn:
            run_inline(conn, module.downgrade)
        with engine.connect() as conn:
            cols = {row[1] for row in conn.exec_driver_sql(
                "PRAGMA table_info(lesson_code_runs)").all()}
            assert "charged" not in cols
    finally:
        engine.dispose()


def test_trial_run_failure_never_touches_tries(tmp_path: Path):
    """试跑不计分，判题挂了也没有次数可退——charged 从头到尾都是 false。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_limited_coding_lesson(app, problem_id_no=no, attempt_limit=1)
    app.state.judge = BrokenJudge()
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    started = start_run(sclient, lid, bid, scope="samples")
    assert started.status_code in (200, 201), started.text
    poll(sclient, lid, bid, started.json()["run_id"])

    state = get_problem(sclient, lid, bid).json()
    assert state["tries"] == 0 and state["tries_left"] == 1
    db = app.state.session_factory()
    try:
        assert db.query(LessonCodeRun).one().charged is False
    finally:
        db.close()


# ---------- 次数与门控 ----------


def test_submit_consumes_tries_and_refuses_when_exhausted(tmp_path: Path):
    """次数由服务端裁决，且在**入队前**扣——判完再扣，连点两次就只扣一次。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_lesson_with_blocks(app, [{
        "block_type": "practice", "title": "编程练习", "problem_id_no": no,
        "score": 20, "display_no": "1", "attempt_limit": 1,
    }])
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    assert submit(sclient, lid, bid).status_code == 201
    assert submit(sclient, lid, bid).status_code == 409
    assert get_problem(sclient, lid, bid).json()["can_answer"] is False


def test_submit_blocked_when_block_locked(tmp_path: Path):
    """顺序锁的块不能提交，且不留记录。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_lesson_with_blocks(app, [
        {"title": "前置图文"},
        {"block_type": "practice", "title": "编程练习", "unlock_rule": "sequential",
         "problem_id_no": no, "score": 20, "display_no": "1"},
    ])
    sclient = student_login(app)
    assert submit(sclient, built["lesson_id"], built["block_ids"][1]).status_code == 403

    db = app.state.session_factory()
    try:
        assert db.query(LessonCodeRun).count() == 0
    finally:
        db.close()


def test_submit_rejects_empty_code(tmp_path: Path):
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    r = submit(sclient, built["lesson_id"], built["block_ids"][-1], code="   ")
    assert r.status_code == 400


# ---------- 代码不丢（文档 18 §3.2 B2） ----------


def test_last_code_is_restored_from_latest_run(tmp_path: Path):
    """跑过一次之后重新取题，编辑器能拿回自己的代码。

    课时页的练习块不在 keep-alive 白名单里，切块必然销毁组件——没有这个字段，
    学生切走再切回来代码就真的没了，而代码是他唯一无法从别处找回的东西。
    """
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    assert get_problem(sclient, lid, bid).json()["question"]["last_code"] == ""
    start_run(sclient, lid, bid, code="print('hello')")
    assert get_problem(sclient, lid, bid).json()["question"]["last_code"] == "print('hello')"


def test_draft_is_saved_and_restored(tmp_path: Path):
    """草稿：写了没跑也不能丢，且不计次、不算已提交。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    draft = "int main(){ /* 写到一半 */ }"
    r = sclient.put(f"/api/lessons/{lid}/blocks/{bid}/draft", headers=scsrf(sclient),
                    json={"language": "cpp", "code": draft})
    assert r.status_code == 200, r.text

    body = get_problem(sclient, lid, bid).json()
    assert body["question"]["last_code"] == draft
    assert body["submitted"] is False and body["tries"] == 0

    db = app.state.session_factory()
    try:
        assert db.query(LessonProblemAttempt).one().tries == 0
    finally:
        db.close()


def test_draft_wins_over_older_run_code(tmp_path: Path):
    """草稿比历史运行记录新，取题要给草稿——否则学生会看到自己刚改之前的版本。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    start_run(sclient, lid, bid, code="print(1)")
    sclient.put(f"/api/lessons/{lid}/blocks/{bid}/draft", headers=scsrf(sclient),
                json={"language": "python", "code": "print(2)"})
    assert get_problem(sclient, lid, bid).json()["question"]["last_code"] == "print(2)"


def test_draft_rejected_on_non_programming(tmp_path: Path):
    """客观题没有草稿这回事 → 400，不是静默写一条脏数据。"""
    from test_lesson_practice import build_practice, seed_choice_problem

    app = build_app(tmp_path)
    no = seed_choice_problem(app, problem_id_no="Q290001")["problem_id_no"]
    built = build_practice(app, problem_id_no=no)
    sclient = student_login(app)
    r = sclient.put(
        f"/api/lessons/{built['lesson_id']}/blocks/{built['block_ids'][-1]}/draft",
        headers=scsrf(sclient), json={"language": "cpp", "code": "x"},
    )
    assert r.status_code == 400


def test_reset_clears_code_too(tmp_path: Path):
    """重做编程题：编辑器也要清干净，只留题面。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    submit(sclient, lid, bid, code="cout<<1;")
    r = reset(sclient, lid, bid)
    assert r.status_code == 200 and r.json()["last_code"] == ""
    assert get_problem(sclient, lid, bid).json()["question"]["last_code"] == ""
