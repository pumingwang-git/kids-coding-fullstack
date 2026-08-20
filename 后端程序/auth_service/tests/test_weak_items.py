import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.attempt_source import from_exam_link, from_lesson_homework
from app.models import (
    AttemptAnswer,
    Base,
    ClassGroup,
    ClassMember,
    Course,
    CourseLesson,
    CourseLessonBlock,
    CourseSection,
    ExamAssignment,
    ExamLink,
    LessonPaperBlock,
    LessonProblemAttempt,
    LessonProblemBlock,
    Paper,
    PaperAttempt,
    PaperQuestion,
    Problem,
    User,
)
from app.results_common import build_item_analysis
from app.weak_items import build_weak_items


def _db(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'weak-items.db'}")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _seed_class(db: Session, users: int = 3):
    course = Course(title="低正确率课包")
    db.add(course)
    db.flush()
    class_group = ClassGroup(name="低正确率班", course_id=course.id, status="active")
    section = CourseSection(course_id=course.id, title="第一章")
    db.add_all([class_group, section])
    db.flush()
    lesson = CourseLesson(course_id=course.id, section_id=section.id, title="第一课")
    db.add(lesson)
    db.flush()
    students = [
        User(username=f"weak-{number}", email=f"weak-{number}@example.com", hashed_password="hash")
        for number in range(users)
    ]
    db.add_all(students)
    db.flush()
    db.add_all(ClassMember(class_id=class_group.id, student_id=student.id) for student in students)
    db.commit()
    return class_group, lesson, students


def _paper(db: Session, *, problem_no: str, title: str):
    problem = Problem(type="choice", title=title, stem="题干", status="approved",
                      problem_id_no=problem_no, version_no=1, revision=1)
    paper = Paper(title=f"{title}卷", status="published")
    db.add_all([problem, paper])
    db.flush()
    problem.root_problem_id = problem.id
    db.add(PaperQuestion(paper_id=paper.id, problem_id_no=problem_no, score=10, sort_order=0))
    db.commit()
    return paper


def test_paper_items_are_the_existing_item_analysis_rows_without_recalculation(tmp_path):
    engine, db = _db(tmp_path)
    try:
        class_group, lesson, students = _seed_class(db)
        homework_paper = _paper(db, problem_no="HW-1", title="作业题")
        exam_paper = _paper(db, problem_no="EX-1", title="考试题")
        homework_block = CourseLessonBlock(
            lesson_id=lesson.id, block_type="homework", title="整卷作业", sort_order=0,
        )
        db.add(homework_block)
        db.flush()
        homework_detail = LessonPaperBlock(block_id=homework_block.id, paper_id=homework_paper.id,
                                            mode="homework")
        link = ExamLink(paper_id=exam_paper.id, name="班级考试", access_token="weak-items-link")
        db.add_all([homework_detail, link])
        db.flush()
        db.add(ExamAssignment(exam_link_id=link.id, target_type="class", target_id=class_group.id))
        outsider = User(username="weak-outsider", email="weak-outsider@example.com",
                        hashed_password="hash")
        db.add(outsider)
        db.flush()

        homework_source = from_lesson_homework(homework_block, homework_detail)
        homework_attempt = PaperAttempt(
            source_type=homework_source.source_type, source_id=homework_source.source_id,
            paper_id=homework_paper.id, user_id=students[0].id, attempt_no=1, total_score=5,
            status="submitted",
        )
        failed_homework_attempt = PaperAttempt(
            source_type=homework_source.source_type, source_id=homework_source.source_id,
            paper_id=homework_paper.id, user_id=students[1].id, attempt_no=1, total_score=0,
            status="submitted",
        )
        outsider_homework_attempt = PaperAttempt(
            source_type=homework_source.source_type, source_id=homework_source.source_id,
            paper_id=homework_paper.id, user_id=outsider.id, attempt_no=1, total_score=0,
            status="submitted",
        )
        exam_source = from_exam_link(link)
        exam_attempt = PaperAttempt(
            source_type=exam_source.source_type, source_id=exam_source.source_id,
            exam_link_id=link.id, paper_id=exam_paper.id, user_id=students[0].id,
            attempt_no=1, total_score=0, status="submitted",
        )
        outsider_exam_attempt = PaperAttempt(
            source_type=exam_source.source_type, source_id=exam_source.source_id,
            exam_link_id=link.id, paper_id=exam_paper.id, user_id=outsider.id,
            attempt_no=1, total_score=10, status="submitted",
        )
        db.add_all([
            homework_attempt, failed_homework_attempt, outsider_homework_attempt, exam_attempt,
            outsider_exam_attempt,
        ])
        db.flush()
        db.add_all([
            AttemptAnswer(attempt_id=homework_attempt.id, problem_id_no="HW-1", score=5,
                          judge_status="judged"),
            AttemptAnswer(attempt_id=failed_homework_attempt.id, problem_id_no="HW-1", score=0,
                          judge_status="failed"),
            AttemptAnswer(attempt_id=outsider_homework_attempt.id, problem_id_no="HW-1", score=0,
                          judge_status="judged"),
            AttemptAnswer(attempt_id=exam_attempt.id, problem_id_no="EX-1", score=0,
                          judge_status="judged"),
            AttemptAnswer(attempt_id=outsider_exam_attempt.id, problem_id_no="EX-1", score=10,
                          judge_status="judged"),
        ])
        db.commit()

        _grouping, homework_expected = build_item_analysis(
            db, homework_paper, [homework_attempt, failed_homework_attempt], "best",
        )
        _grouping, exam_expected = build_item_analysis(db, exam_paper, [exam_attempt], "best")
        actual = build_weak_items(db, class_group.id)

        homework_actual = next(
            item for item in actual
            if (item["source"], item["source_id"]) == ("lesson_homework", homework_block.id)
        )
        exam_actual = next(
            item for item in actual
            if (item["source"], item["source_id"]) == ("exam_link", link.id)
        )
        assert {key: value for key, value in homework_actual.items() if key not in {
            "source", "source_id", "source_title"
        }} == homework_expected[0]
        assert {key: value for key, value in exam_actual.items() if key not in {
            "source", "source_id", "source_title"
        }} == exam_expected[0]
        assert homework_actual["judge_failed"] == 1
        assert homework_actual["score_rate"] == 0.5
    finally:
        db.close()
        engine.dispose()


def test_practice_rate_is_based_on_people_not_attempt_count(tmp_path):
    engine, db = _db(tmp_path)
    try:
        class_group, lesson, students = _seed_class(db)
        problem = Problem(type="choice", title="课中题", stem="题干", status="approved",
                          problem_id_no="PR-1", version_no=1, revision=1)
        block = CourseLessonBlock(lesson_id=lesson.id, block_type="practice", title="课中练习",
                                  sort_order=0)
        db.add_all([problem, block])
        db.flush()
        problem.root_problem_id = problem.id
        db.add(LessonProblemBlock(block_id=block.id, problem_id_no=problem.problem_id_no,
                                  problem_type=problem.type, display_no="1", score=10))
        outsider = User(username="practice-outsider", email="practice-outsider@example.com",
                        hashed_password="hash")
        db.add(outsider)
        db.flush()
        db.add_all([
            LessonProblemAttempt(user_id=students[0].id, block_id=block.id, lesson_id=lesson.id,
                                 tries=4, last_correct=True),
            LessonProblemAttempt(user_id=students[1].id, block_id=block.id, lesson_id=lesson.id,
                                 tries=1, last_correct=False),
            LessonProblemAttempt(user_id=students[2].id, block_id=block.id, lesson_id=lesson.id,
                                 tries=2, last_correct=False),
            LessonProblemAttempt(user_id=outsider.id, block_id=block.id, lesson_id=lesson.id,
                                 tries=1, last_correct=True),
        ])
        db.commit()

        actual = build_weak_items(db, class_group.id)
        assert actual == [{
            "source": "lesson_practice", "source_id": block.id, "source_title": "课中练习",
            "sort_order": "1", "problem_id_no": "PR-1", "full_score": 10,
            "type": "choice", "title": "课中题", "missing": False,
            "answered": 3, "correct": 1, "score_rate": 0.3333,
        }]
    finally:
        db.close()
        engine.dispose()


def test_empty_class_has_no_weak_items(tmp_path):
    engine, db = _db(tmp_path)
    try:
        class_group, _lesson, _students = _seed_class(db, users=0)
        assert build_weak_items(db, class_group.id) == []
    finally:
        db.close()
        engine.dispose()
