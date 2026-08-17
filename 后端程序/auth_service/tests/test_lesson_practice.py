"""课中练习单题作答（形态 A · 块内直答）回归。

对应《15、课时作答与资料展示-开发交接》第三节与 §11 验收 3/4。

三条红线的回归：
- 取题接口**不下发答案、不下发解析、不下发 problem_id_no**（递归断言，照抄
  test_exam.py 的 walk_keys 传统）；
- 判分只走 app/scoring.py，与考试页同一套逻辑；
- 两道闸门都要过，锁定块不能取题也不能作答。

外加作答语义：提交即完成（不论对错）、次数由服务端裁决、刷新不丢作答。
"""
import json
from pathlib import Path

from test_admin_course_content import seed_problem
from test_exam import admin_login, build_app, find_answer_keys, scsrf, student_login, walk_keys
from test_lesson_block_unlock import build_lesson_with_blocks, complete

from app.models import ChoiceOption, FillAnswer, LessonBlockCompletion, LessonProblemAttempt, Problem

# ---------- 辅助 ----------


def seed_choice_problem(app, *, problem_id_no="Q200001", multi=False, analysis="因为 A 才对。"):
    """建一道带选项的选择/多选题（A 正确；多选时 A、C 正确）。"""
    db = app.state.session_factory()
    try:
        p = Problem(
            type="multi_choice" if multi else "choice",
            title="题", stem="下面哪个对？", status="approved", analysis=analysis,
            problem_id_no=problem_id_no, version_no=1, revision=1,
        )
        db.add(p)
        db.flush()
        p.root_problem_id = p.id
        for i, (label, ok) in enumerate([("A", True), ("B", False), ("C", multi), ("D", False)]):
            db.add(ChoiceOption(problem_id=p.id, option_label=label,
                                content=f"选项{label}", is_correct=ok, sort_order=i))
        db.commit()
        return {"problem_id_no": p.problem_id_no}
    finally:
        db.close()


def seed_fill_problem(app, *, problem_id_no="Q200009"):
    """建一道两空填空题（b1=main，b2=0）。"""
    db = app.state.session_factory()
    try:
        p = Problem(type="fill", title="填空", stem="C++ 从 [[b1]] 开始，返回 [[b2]]",
                    status="approved", analysis="入口是 main。",
                    problem_id_no=problem_id_no, version_no=1, revision=1)
        db.add(p)
        db.flush()
        p.root_problem_id = p.id
        db.add(FillAnswer(problem_id=p.id, blank_index=0, blank_key="b1", answer="main"))
        db.add(FillAnswer(problem_id=p.id, blank_index=1, blank_key="b2", answer="0"))
        db.commit()
        return {"problem_id_no": p.problem_id_no}
    finally:
        db.close()


def build_practice(app, *, problem_id_no, score=10, attempt_limit=0,
                   show_analysis=True, shuffle_options=False, extra_blocks=()):
    """建一节课时：可选前置块 + 一个绑定单题的 practice 块，发布。"""
    blocks = [dict(b) for b in extra_blocks]
    blocks.append({
        "block_type": "practice", "title": "课中练习",
        "problem_id_no": problem_id_no, "score": score, "display_no": "1",
        "attempt_limit": attempt_limit, "show_analysis": show_analysis,
        "shuffle_options": shuffle_options,
    })
    return build_lesson_with_blocks(app, blocks)


def get_problem(sclient, lesson_id, block_id):
    return sclient.get(f"/api/lessons/{lesson_id}/blocks/{block_id}/problem")


def answer(sclient, lesson_id, block_id, ans):
    return sclient.post(f"/api/lessons/{lesson_id}/blocks/{block_id}/answer",
                        headers=scsrf(sclient), json={"answer": ans})


# ---------- 红线 1/2：取题不泄题 ----------


def test_problem_delivery_leaks_nothing(tmp_path: Path):
    """取题响应里**不得出现**答案、解析、题目身份与对错标记（递归断言）。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no)
    sclient = student_login(app)
    bid = built["block_ids"][-1]

    resp = get_problem(sclient, built["lesson_id"], bid)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    walk_keys(body, {"problem_id_no", "analysis", "is_correct", "answer_json",
                     "problem_id", "root_problem_id"})
    # 选项只给 label + content，一个对错标记都不能有
    assert [o["label"] for o in body["question"]["options"]] == ["A", "B", "C", "D"]
    for opt in body["question"]["options"]:
        assert set(opt) == {"label", "content"}
    assert "verdict" not in body, "还没作答就不该有判定"


def test_analysis_only_after_submit(tmp_path: Path):
    """解析只在提交后出现；show_analysis=False 时永不出现。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app, analysis="独门解析文本")["problem_id_no"]
    built = build_practice(app, problem_id_no=no, show_analysis=True)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    assert "独门解析文本" not in get_problem(sclient, lid, bid).text
    body = answer(sclient, lid, bid, {"picked": "A"}).json()
    assert body["verdict"]["analysis"] == "独门解析文本"

    # 关掉 show_analysis 的另一节课时：提交后也不给
    no2 = seed_choice_problem(app, problem_id_no="Q200002", analysis="不该出现")["problem_id_no"]
    b2 = build_practice(app, problem_id_no=no2, show_analysis=False)
    r2 = answer(sclient, b2["lesson_id"], b2["block_ids"][-1], {"picked": "A"})
    assert r2.status_code == 200
    assert "analysis" not in r2.json()["verdict"]
    assert "不该出现" not in r2.text


def test_verdict_detail_never_carries_answer_keys(tmp_path: Path):
    """判定明细不得携带标准答案。

    这里**没有任何闸门**能挡住它：show_analysis 只管解析文本，verdict.detail 是
    无条件下发的。少了裁剪，配 show_analysis=False + attempt_limit=3 的练习，
    学生第一次随便答，从 detail.correct 读出答案，第二次必满分——attempt_limit
    与 show_analysis 两个配置项一起失效。
    """
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]  # A 正确
    built = build_practice(app, problem_id_no=no, show_analysis=False, attempt_limit=3)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    wrong = answer(sclient, lid, bid, {"picked": "D"}).json()
    assert wrong["verdict"]["is_correct"] is False
    leaked = find_answer_keys(wrong)
    assert leaked == [], f"答错后的判定泄露了标准答案：{leaked}"
    # 判定本身照给：学生要知道自己答错了，只是不该知道正确答案是哪个
    assert wrong["verdict"]["detail"]["picked"] == "D"

    # 重新取题（刷新页面）走的是另一条序列化路径，同样不能漏
    assert find_answer_keys(get_problem(sclient, lid, bid).json()) == []


# ---------- 判分（复用 scoring.py） ----------


def test_choice_scoring(tmp_path: Path):
    """单选：答对给满分，答错 0 分，两次都有判定明细。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no, score=10)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    ok = answer(sclient, lid, bid, {"picked": "A"}).json()
    assert ok["verdict"]["is_correct"] is True and ok["verdict"]["score"] == 10

    wrong = answer(sclient, lid, bid, {"picked": "B"}).json()
    assert wrong["verdict"]["is_correct"] is False and wrong["verdict"]["score"] == 0


def test_fill_scoring(tmp_path: Path):
    """填空：按空判分，全对满分。"""
    app = build_app(tmp_path)
    no = seed_fill_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no, score=10)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    body = get_problem(sclient, lid, bid).json()
    assert body["question"]["blank_keys"] == ["b1", "b2"]
    assert "answer" not in str(body["question"]), "填空的标准答案不能随题下发"

    ok = answer(sclient, lid, bid, {"blanks": {"b1": "main", "b2": "0"}}).json()
    assert ok["verdict"]["is_correct"] is True and ok["verdict"]["score"] == 10


# ---------- 作答语义 ----------


def test_submit_completes_block_even_when_wrong(tmp_path: Path):
    """提交即完成，不论对错——练习是学的过程，按对错才算完成会把人卡死在一道题上。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    answer(sclient, lid, bid, {"picked": "B"})  # 答错
    blocks = sclient.get(f"/api/lessons/{lid}").json()["blocks"]
    target = next(b for b in blocks if b["id"] == bid)
    assert target["completed"] is True

    db = app.state.session_factory()
    try:
        row = db.query(LessonBlockCompletion).filter_by(block_id=bid).one()
        assert row.source == "practice"
    finally:
        db.close()


def test_attempt_limit_enforced_server_side(tmp_path: Path):
    """次数由服务端裁决：用完第 3 次必须 409，光靠前端计数刷新就绕过去了。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no, attempt_limit=2)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    assert answer(sclient, lid, bid, {"picked": "B"}).status_code == 200
    third = answer(sclient, lid, bid, {"picked": "C"})
    assert third.status_code == 200 and third.json()["tries_left"] == 0
    assert third.json()["can_answer"] is False

    blocked = answer(sclient, lid, bid, {"picked": "A"})
    assert blocked.status_code == 409

    db = app.state.session_factory()
    try:
        assert db.query(LessonProblemAttempt).filter_by(block_id=bid).one().tries == 2
    finally:
        db.close()


def test_answer_survives_reload(tmp_path: Path):
    """刷新不丢作答：重新取题带回上次的作答与判定。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    answer(sclient, lid, bid, {"picked": "B"})
    again = get_problem(sclient, lid, bid).json()
    assert again["answer"] == {"picked": "B"}
    assert again["submitted"] is True
    assert again["verdict"]["is_correct"] is False
    assert again["tries"] == 1


def test_shuffle_is_stable_across_reloads(tmp_path: Path):
    """选项乱序必须是确定性的：刷新重排会让「我上次选的 B」对不上。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no, shuffle_options=True)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    first = [o["content"] for o in get_problem(sclient, lid, bid).json()["question"]["options"]]
    second = [o["content"] for o in get_problem(sclient, lid, bid).json()["question"]["options"]]
    assert first == second


# ---------- 门控 ----------


def test_locked_block_cannot_be_read_or_answered(tmp_path: Path):
    """顺序锁的练习块：取题与作答都 403，且不写任何作答记录。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_lesson_with_blocks(app, [
        {"title": "前置图文"},
        {"block_type": "practice", "title": "课中练习", "unlock_rule": "sequential",
         "problem_id_no": no, "score": 10, "display_no": "1"},
    ])
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][1]

    assert get_problem(sclient, lid, bid).status_code == 403
    assert answer(sclient, lid, bid, {"picked": "A"}).status_code == 403

    db = app.state.session_factory()
    try:
        assert db.query(LessonProblemAttempt).count() == 0
    finally:
        db.close()

    # 完成前置块后解锁，立刻可取题
    complete(sclient, lid, built["block_ids"][0])
    assert get_problem(sclient, lid, bid).status_code == 200


def test_block_from_other_lesson_404(tmp_path: Path):
    """拿别的课时的 block_id 来取题 → 404。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    a = build_practice(app, problem_id_no=no)
    b = build_practice(app, problem_id_no=seed_choice_problem(
        app, problem_id_no="Q200003")["problem_id_no"])
    sclient = student_login(app)
    assert get_problem(sclient, a["lesson_id"], b["block_ids"][-1]).status_code == 404


def test_non_practice_block_rejected(tmp_path: Path):
    """对图文块调作答接口 → 400，不是 500。"""
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [{"title": "图文"}])
    sclient = student_login(app)
    r = get_problem(sclient, built["lesson_id"], built["block_ids"][0])
    assert r.status_code == 400


def test_programming_rejected_on_answer_endpoint(tmp_path: Path):
    """编程题走运行/提交链路，不走本接口 → 400 而不是判 0 分。"""
    app = build_app(tmp_path)
    seeded = seed_problem(app, type="programming", problem_id_no="Q200055")
    built = build_practice(app, problem_id_no=seeded["problem_id_no"])
    sclient = student_login(app)
    r = answer(sclient, built["lesson_id"], built["block_ids"][-1], {"picked": "A"})
    assert r.status_code == 400


# ---------- 重做（文档 18 §2.4） ----------


def reset(sclient, lesson_id, block_id):
    return sclient.post(f"/api/lessons/{lesson_id}/blocks/{block_id}/reset",
                        headers=scsrf(sclient))


def test_reset_clears_answer_but_keeps_tries_and_completion(tmp_path: Path):
    """重做只清作答态：tries 不变、完成记录不动，作答区回到可作答。

    这三条是重做能不能上线的全部：清了完成记录，学生复习一道题就会被顺序锁
    踢回闯关起点；返还了次数，限次就成了摆设。
    """
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no, score=10, attempt_limit=3)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    answer(sclient, lid, bid, {"picked": "B"})  # 先答错一次
    body = reset(sclient, lid, bid).json()
    assert body["submitted"] is False and "verdict" not in body
    assert body["answer"] in (None, {}), "作答内容要清干净"
    assert body["tries"] == 1 and body["tries_left"] == 2, "重做不消耗、也不返还次数"
    assert body["can_answer"] is True

    db = app.state.session_factory()
    try:
        attempt = db.query(LessonProblemAttempt).one()
        assert attempt.last_score is None and attempt.last_correct is None
        assert attempt.reset_count == 1 and attempt.last_reset_at is not None
        # 完成记录只增不减
        assert db.query(LessonBlockCompletion).filter_by(block_id=bid).count() == 1
    finally:
        db.close()

    # 刷新页面（重新取题）不该把判定弹回来
    again = get_problem(sclient, lid, bid).json()
    assert again["submitted"] is False and "verdict" not in again


def test_reset_allowed_when_attempts_exhausted(tmp_path: Path):
    """次数用尽也能重做，但 can_answer 仍是 false——复习和刷分是两件事。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no, attempt_limit=1)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    answer(sclient, lid, bid, {"picked": "B"})
    body = reset(sclient, lid, bid).json()
    assert body["submitted"] is False
    assert body["can_answer"] is False and body["tries_left"] == 0
    # 清空之后仍然交不上去
    assert answer(sclient, lid, bid, {"picked": "A"}).status_code == 409


def test_self_test_state_serves_analysis_but_never_the_answer(tmp_path: Path):
    """次数用尽后重做 = 自测态：给解析文本，但一个正确答案都不给。

    没有解析的话这条路是死胡同——提交按钮禁着、判定区不显示，学生答完拿不到
    任何反馈，「复习自测」这个设计目标在最后一公里断掉。

    放行的边界同样要钉死：**只有解析文本**。verdict.detail 里带着正确选项 label
    （所以正常判定要走 strip_answer_keys），顺着自测态漏出去等于给 show_analysis
    开后门。这条测试守的就是那个边界。
    """
    app = build_app(tmp_path)
    no = seed_choice_problem(app, analysis="自测态该看到的解析")["problem_id_no"]
    built = build_practice(app, problem_id_no=no, attempt_limit=1, show_analysis=True)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    answer(sclient, lid, bid, {"picked": "B"})  # 用掉唯一一次
    body = reset(sclient, lid, bid).json()

    assert body["self_test"] is True and body["can_answer"] is False
    assert body["analysis"] == "自测态该看到的解析"
    assert "verdict" not in body, "自测态没有判定——这次根本没判分"
    # 红线：解析放行了，答案与对错明细一个字都不能跟着出来
    walk_keys(body, {"is_correct", "correct", "detail", "answer_json", "problem_id_no"})
    assert not find_answer_keys(body)

    # 刷新（重新取题）仍在自测态，解析要稳定给到，不能只在 reset 的那一响里出现
    again = get_problem(sclient, lid, bid).json()
    assert again["self_test"] is True and again["analysis"] == "自测态该看到的解析"


def test_self_test_respects_show_analysis_off(tmp_path: Path):
    """show_analysis=False 的题，自测态也不给解析——自测态不是绕开开关的后门。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app, analysis="不该出现的解析")["problem_id_no"]
    built = build_practice(app, problem_id_no=no, attempt_limit=1, show_analysis=False)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    answer(sclient, lid, bid, {"picked": "B"})
    body = reset(sclient, lid, bid).json()
    assert "self_test" not in body and "analysis" not in body
    assert "不该出现的解析" not in reset(sclient, lid, bid).text
    assert "不该出现的解析" not in get_problem(sclient, lid, bid).text


def test_unlimited_attempts_never_enter_self_test(tmp_path: Path):
    """不限次数的题永远进不了自测态：它随时能再交一次，走正常判定就行。

    这条挡的是把解析下发条件写成 `not submitted` 的写法——那样一来，
    任何一道不限次的题只要重做一下就能白拿解析，show_analysis 直接失效。
    """
    app = build_app(tmp_path)
    no = seed_choice_problem(app, analysis="不限次不该白给")["problem_id_no"]
    built = build_practice(app, problem_id_no=no, attempt_limit=0, show_analysis=True)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    answer(sclient, lid, bid, {"picked": "B"})
    body = reset(sclient, lid, bid).json()
    assert body["can_answer"] is True
    assert "self_test" not in body and "analysis" not in body
    assert "不限次不该白给" not in reset(sclient, lid, bid).text


def test_reset_does_not_relock_following_block(tmp_path: Path):
    """重做前置练习，不能把后面已解锁的顺序锁块重新锁上。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_lesson_with_blocks(app, [
        {"block_type": "practice", "title": "课中练习",
         "problem_id_no": no, "score": 10, "display_no": "1"},
        {"title": "后续图文", "unlock_rule": "sequential"},
    ])
    sclient = student_login(app)
    lid, first, second = built["lesson_id"], built["block_ids"][0], built["block_ids"][1]

    answer(sclient, lid, first, {"picked": "A"})
    blocks = sclient.get(f"/api/lessons/{lid}").json()["blocks"]
    assert blocks[1]["lock_reason"] is None, "答完前置块，后面应已解锁"

    reset(sclient, lid, first)
    blocks = sclient.get(f"/api/lessons/{lid}").json()["blocks"]
    assert blocks[1]["lock_reason"] is None, "重做不该把已解锁的块重新锁上"
    assert blocks[0]["completed"] is True


def test_reset_is_idempotent_without_attempt(tmp_path: Path):
    """没作答过就重做：不报错，回当前状态。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no)
    sclient = student_login(app)
    r = reset(sclient, built["lesson_id"], built["block_ids"][-1])
    assert r.status_code == 200 and r.json()["submitted"] is False


def test_reset_without_attempt_creates_no_row(tmp_path: Path):
    """幂等快路径不能建行：重做一道没做过的题，库里不该多出一条空作答记录。

    加锁修复是「有记录才升级成锁读」，因为 _lock_attempt 取不到就会 INSERT。
    这条守住那个 if——否则每点一次重做都在攒垃圾行，attempt 表会被没作答过的
    记录撑起来，"有没有作答记录"也不再能当作判断依据。
    """
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no)
    sclient = student_login(app)
    reset(sclient, built["lesson_id"], built["block_ids"][-1])

    db = app.state.session_factory()
    try:
        assert db.query(LessonProblemAttempt).count() == 0
    finally:
        db.close()


def test_reset_locks_the_attempt_row_on_postgresql(tmp_path: Path, monkeypatch):
    """重做读 attempt 的那条 SELECT，在生产方言下必须带 FOR UPDATE。

    **为什么不写成两个线程的并发用例**：测试跑在 SQLite 上，而 SQLite 的
    with_for_update() 是 no-op（见 _lock_attempt 的注释），并发用例在这里只会
    因为 SQLite 自己的文件级写锁而通过，证明不了生产 PostgreSQL 上的行为——
    那种测试比没有更糟，它会在真正回归时继续绿灯。

    所以直接抓真实语句、按生产方言编译了看。不复刻一份 select 是有意的：
    复刻的那份跟着测试走，改坏 _lock_attempt 也照样绿。

    守的是什么：提交（submit_practice_answer / submit_lesson_code）判分期间持着
    这把行锁。重做若不抢同一把锁，就会在提交落库后把刚写好的作答与判定清掉，
    留下 tries 已 +1、answer_json 为空的中间态——次数消耗了，成绩没了。
    """
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.orm import Session as SASession

    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=no, attempt_limit=3)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]
    answer(sclient, lid, bid, {"picked": "A"})  # 先作答，让重做走到加锁分支

    seen = []
    original = SASession.scalar

    def spy(self, statement, *args, **kwargs):
        seen.append(statement)
        return original(self, statement, *args, **kwargs)

    monkeypatch.setattr(SASession, "scalar", spy)
    assert reset(sclient, lid, bid).status_code == 200

    locked = [
        st for st in seen
        if "lesson_problem_attempts" in str(st)
        and "FOR UPDATE" in str(st.compile(dialect=postgresql.dialect()))
    ]
    assert locked, "重做没有对 attempt 行加锁，会与并发提交互相覆盖"


def test_reset_blocked_when_block_locked(tmp_path: Path):
    """顺序锁的块不能重做——两道闸门对每个写接口都成立。"""
    app = build_app(tmp_path)
    no = seed_choice_problem(app)["problem_id_no"]
    built = build_lesson_with_blocks(app, [
        {"title": "前置图文"},
        {"block_type": "practice", "title": "课中练习", "unlock_rule": "sequential",
         "problem_id_no": no, "score": 10, "display_no": "1"},
    ])
    sclient = student_login(app)
    assert reset(sclient, built["lesson_id"], built["block_ids"][1]).status_code == 403
