"""纯图题干 / 纯图选项必须能提交审核。

启用配图之后立刻会撞上的第一个问题，不是边角情况：几何题、图形推理题的题干就是
一张图加一句"如图"甚至只有一张图，图形选择题的四个选项本身就是四张图。
而派生纯文本的 `_markdown_text()` 会把 `![](...)` 整个剥掉——直接拿它判空，
这两类题一道都录不进来。
"""

from test_exam import admin_login, build_app, common, match

IMAGE = "![](/media/ab/" + "c" * 64 + ".png)"


def image_choice_payload(stem: str, options: list[str]) -> dict:
    return {
        "type": "choice", "sub_type": None, "common": common(),
        "stem": stem, "analysis": "", "blanks": [], "programming": None,
        "options": [{"content": content, "is_correct": index == 0}
                    for index, content in enumerate(options)],
    }


def create_and_submit(client, headers, payload):
    created = client.post("/api/admin/problems", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    problem = created.json()
    submitted = client.post(f"/api/admin/problems/{problem['id']}/submit",
                            headers=match(headers, problem["revision"]))
    return problem, submitted


def test_image_only_stem_can_be_submitted(tmp_path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)

    _problem, submitted = create_and_submit(
        client, headers, image_choice_payload(IMAGE, ["对", "错"]))
    assert submitted.status_code == 200, submitted.text


def test_image_only_options_can_be_submitted(tmp_path):
    """图形选择题：题干是文字，四个选项各是一张图。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)

    _problem, submitted = create_and_submit(
        client, headers, image_choice_payload("选出与左图旋转 90° 后一致的图形", [IMAGE] * 4))
    assert submitted.status_code == 200, submitted.text


def test_image_only_stem_gets_a_readable_title(tmp_path):
    """列表里那一行不能是完全空白的——纯图题干派生不出文字，给可辨识的占位。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)

    created = client.post("/api/admin/problems", headers=headers,
                          json=image_choice_payload(IMAGE, ["对", "错"]))
    assert created.status_code == 201, created.text

    listed = client.get("/api/admin/problems", headers=headers).json()["items"]
    row = next(item for item in listed if item["id"] == created.json()["id"])
    assert row["stem"] == IMAGE          # 题干原样保留，只有派生的标题是占位
    detail = client.get(f"/api/admin/problems/{row['id']}", headers=headers)
    assert detail.status_code == 200


def test_truly_empty_stem_is_still_rejected(tmp_path):
    """放宽的只是"图算内容"，空题干仍然必须拦住。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)

    _problem, submitted = create_and_submit(
        client, headers, image_choice_payload("   ", ["对", "错"]))
    assert submitted.status_code == 422
    assert "题干" in submitted.json()["detail"]


def test_empty_option_is_still_rejected(tmp_path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)

    _problem, submitted = create_and_submit(
        client, headers, image_choice_payload("如图", [IMAGE, "  "]))
    assert submitted.status_code == 422
    assert "选项" in submitted.json()["detail"]


SIZED_IMAGE = "![三角形|50%](/media/ab/" + "c" * 64 + ".png)"
LEGACY_IMAGE = '<img src="/media/ab/' + "c" * 64 + '.png" width="50%">'


def test_sized_image_still_counts_as_content(tmp_path):
    """带尺寸后缀的图也得算内容。

    尺寸档位写进 alt 的尾部（`![三角形|50%](...)`，见前端 admin-markdown.js 的
    IMAGE_WIDTHS）。这仍是标准的 Markdown 图片语法，`_MD_IMAGE_RE` 原样认得——
    这条用例盯的就是"改尺寸载体时别把它改成正则认不出的形状"。
    """
    app = build_app(tmp_path)
    client, headers = admin_login(app)

    _problem, submitted = create_and_submit(
        client, headers, image_choice_payload(SIZED_IMAGE, ["对", "错"]))
    assert submitted.status_code == 200, submitted.text


def test_legacy_inline_img_still_derives_a_readable_title():
    """尺寸档位一度把图改写成内联 `<img>`，那阵子存下的题干库里可能还有。

    不认这种写法的话，纯图题的派生标题会是一整行 `<img src="/media/…" width="50%">`：
    `_markdown_text()` 刻意不剥 `<...>`（为了 `vector<int>`），于是这行标签整个当了标题。
    派生标题只在 /problems/pickable 上露出来，而那条路要求题目已 approved，
    绕一整圈审核流程只为看一个字符串不划算——直接对着派生函数断言。
    """
    from app.routers.admin_questions import _display_title, _has_content

    assert _display_title("choice", LEGACY_IMAGE) == "[图片单选题]"
    assert _display_title("choice", SIZED_IMAGE) == "[图片单选题]"
    assert _has_content(LEGACY_IMAGE)
    # 单挑 <img> 剥掉，不能顺手把题面里的 C++ 尖括号也吃了
    assert _display_title("choice", "vector<int> 与 #include <iostream>") == (
        "vector<int> 与 #include <iostream>"
    )
