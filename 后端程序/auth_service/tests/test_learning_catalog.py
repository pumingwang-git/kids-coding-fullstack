"""数据驱动专区、分类树、课程类型和标签的契约测试。"""
from pathlib import Path

from test_admin_courses import add_lesson, add_section
from test_exam import admin_login, build_app, student_login


def test_public_catalog_and_nested_category_filter(tmp_path: Path):
    app = build_app(tmp_path)
    admin, headers = admin_login(app)
    areas = admin.get("/api/learning-areas").json()["items"]
    assert [item["key"] for item in areas] == ["kids", "programmer"]
    assert areas[0]["modules"][0]["module_key"] == "overview"

    tree = admin.get("/api/course-taxonomy?area_key=kids").json()["items"]
    cpp = next(item for item in tree if item["name"] == "C/C++")
    basic = next(item for item in cpp["children"] if item["name"] == "C++ 基础")
    project_tag = next(
        item for item in admin.get(
            "/api/admin/learning-catalog/tags?area_key=kids", headers=headers
        ).json() if item["key"] == "project-based"
    )
    created = admin.post("/api/admin/courses", headers=headers, json={
        "title": "真实 C++ 课程", "area_key": "kids", "course_kind": "systematic",
        "category_id": basic["id"], "tag_ids": [project_tag["id"]], "difficulty": "beginner",
    })
    assert created.status_code == 201, created.text
    course = created.json()
    section = add_section(admin, headers, course["id"]).json()
    add_lesson(admin, headers, section["id"], "第一课")
    assert admin.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200

    student = student_login(app)
    by_direction = student.get(f"/api/courses?area_key=kids&category_id={cpp['id']}").json()
    assert [item["id"] for item in by_direction["items"]] == [course["id"]]
    assert [item["name"] for item in by_direction["items"][0]["category_breadcrumb"]] == [
        "C/C++", "C++ 基础",
    ]
    available_tags = student.get(
        f"/api/course-tags?area_key=kids&course_kind=systematic&category_id={cpp['id']}"
    ).json()["items"]
    assert available_tags == [{
        "id": project_tag["id"], "key": "project-based", "name": "项目制",
        "sort_order": 10, "course_count": 1,
    }]


def test_hidden_module_survives_admin_roundtrip(tmp_path: Path):
    """隐藏模块对学生端不下发，但管理端必须看得见，且原样回写不能把它删掉。

    回归 A1：serialize_area() 曾对管理端也滤掉 hidden，那一行从界面消失后，
    下一次「保存导航」（整表替换）会连同标签名和排序一起真删。
    """
    app = build_app(tmp_path)
    admin, headers = admin_login(app)
    assert admin.put("/api/admin/learning-catalog/areas/kids/modules", headers=headers, json=[
        {"module_key": "overview", "label": "学习首页", "status": "available", "sort_order": 10},
        {"module_key": "courses", "label": "课程", "status": "available", "sort_order": 20},
        {"module_key": "explore", "label": "探索创作", "status": "hidden", "sort_order": 40},
    ]).status_code == 200

    def admin_kids():
        rows = admin.get("/api/admin/learning-catalog/areas", headers=headers).json()
        return next(item for item in rows if item["key"] == "kids")["modules"]

    # 管理端看得到隐藏行，学生端看不到
    assert [(m["module_key"], m["status"]) for m in admin_kids()] == [
        ("overview", "available"), ("courses", "available"), ("explore", "hidden"),
    ]
    public = admin.get("/api/learning-areas").json()["items"]
    kids_public = next(item for item in public if item["key"] == "kids")["modules"]
    assert [m["module_key"] for m in kids_public] == ["overview", "courses"]

    # 把管理端看到的内容原样存回去，隐藏行必须还在（这一步以前会把它删掉）
    assert admin.put(
        "/api/admin/learning-catalog/areas/kids/modules", headers=headers,
        json=[{k: m[k] for k in ("module_key", "label", "status", "sort_order")} for m in admin_kids()],
    ).status_code == 200
    explore = next(m for m in admin_kids() if m["module_key"] == "explore")
    assert explore["status"] == "hidden"
    assert explore["label"] == "探索创作"
    assert explore["sort_order"] == 40


def test_module_registry_and_navigation_guards(tmp_path: Path):
    """能力注册表下发、未实现能力禁标可使用、导航必须保留 overview。"""
    app = build_app(tmp_path)
    admin, headers = admin_login(app)

    registry = admin.get("/api/admin/learning-catalog/module-registry", headers=headers).json()
    by_key = {item["module_key"]: item for item in registry}
    # 题库和工具箱以前是前端硬编码兜底，后端不认；现在必须是合法能力
    assert by_key["question-bank"]["implemented"] is True
    assert by_key["toolbox"]["implemented"] is True
    assert by_key["paths"]["implemented"] is False

    # 种子补齐后，两个专区都带上题库和工具箱（删掉前端兜底后行为才不变）
    for area in admin.get("/api/learning-areas").json()["items"]:
        keys = [module["module_key"] for module in area["modules"]]
        assert "question-bank" in keys and "toolbox" in keys, area["key"]

    base = {"module_key": "overview", "label": "学习首页", "status": "available", "sort_order": 10}
    # 没有真实页面的能力不能标成「可使用」
    rejected = admin.put("/api/admin/learning-catalog/areas/kids/modules", headers=headers, json=[
        base, {"module_key": "paths", "label": "学习路线", "status": "available", "sort_order": 20},
    ])
    assert rejected.status_code == 400
    assert "还没有真实页面" in rejected.json()["detail"]
    # 同一个能力配成规划中则放行
    assert admin.put("/api/admin/learning-catalog/areas/kids/modules", headers=headers, json=[
        base, {"module_key": "paths", "label": "学习路线", "status": "planning", "sort_order": 20},
    ]).status_code == 200

    # 清空导航或丢掉 overview 都会让学生端专区首页失去入口
    assert admin.put(
        "/api/admin/learning-catalog/areas/kids/modules", headers=headers, json=[],
    ).status_code == 400
    assert admin.put("/api/admin/learning-catalog/areas/kids/modules", headers=headers, json=[
        {"module_key": "courses", "label": "课程", "status": "available", "sort_order": 20},
    ]).status_code == 400


def test_dynamic_area_type_tag_and_cross_area_validation(tmp_path: Path):
    app = build_app(tmp_path)
    admin, headers = admin_login(app)
    created = admin.post("/api/admin/learning-catalog/areas", headers=headers, json={
        "key": "certification", "name": "考证专区", "status": "planning", "sort_order": 30,
    })
    assert created.status_code == 201, created.text
    assert admin.put("/api/admin/learning-catalog/areas/certification/modules", headers=headers, json=[
        {"module_key": "overview", "label": "专区概览", "status": "available", "sort_order": 10},
        {"module_key": "courses", "label": "课程", "status": "planning", "sort_order": 20},
    ]).status_code == 200
    category = admin.post("/api/admin/learning-catalog/categories", headers=headers, json={
        "area_key": "certification", "key": "network", "name": "网络认证",
    }).json()
    course_type = admin.post("/api/admin/learning-catalog/types", headers=headers, json={
        "area_key": "certification", "key": "bootcamp", "name": "训练营",
    }).json()
    tag = admin.post("/api/admin/learning-catalog/tags", headers=headers, json={
        "area_key": "certification", "key": "beginner", "name": "入门",
    }).json()
    course = admin.post("/api/admin/courses", headers=headers, json={
        "title": "网络认证训练营", "area_key": "certification", "course_kind": course_type["key"],
        "category_id": category["id"], "tag_ids": [tag["id"]], "difficulty": "beginner",
    })
    assert course.status_code == 201, course.text
    assert course.json()["tags"][0]["name"] == "入门"

    kids_category = admin.get("/api/admin/learning-catalog/categories?area_key=kids", headers=headers).json()[0]
    invalid = admin.post("/api/admin/courses", headers=headers, json={
        "title": "错误归属", "area_key": "certification", "course_kind": "bootcamp",
        "category_id": kids_category["id"], "difficulty": "beginner",
    })
    assert invalid.status_code == 400

    # 已被课包引用的专区、类型、分类和标签均不能删除，只能停用。
    assert admin.delete("/api/admin/learning-catalog/areas/certification", headers=headers).status_code == 409
    assert admin.delete(f"/api/admin/learning-catalog/types/{course_type['id']}", headers=headers).status_code == 409
    assert admin.delete(f"/api/admin/learning-catalog/categories/{category['id']}", headers=headers).status_code == 409
    assert admin.delete(f"/api/admin/learning-catalog/tags/{tag['id']}", headers=headers).status_code == 409

    # 稳定标识和专区归属是课程查询、路由及关联表的身份字段，不能借由更新接口破坏。
    changed_category = {**category, "key": "network-v2"}
    assert admin.put(
        f"/api/admin/learning-catalog/categories/{category['id']}", headers=headers, json=changed_category
    ).status_code == 409
    changed_type = {**course_type, "area_key": "kids"}
    assert admin.put(
        f"/api/admin/learning-catalog/types/{course_type['id']}", headers=headers, json=changed_type
    ).status_code == 409
    changed_tag = {**tag, "key": "starter"}
    assert admin.put(
        f"/api/admin/learning-catalog/tags/{tag['id']}", headers=headers, json=changed_tag
    ).status_code == 409
