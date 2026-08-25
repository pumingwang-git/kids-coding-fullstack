"""学生端自由作品：创作、保存、分享到广场，以及公开作品的画廊浏览。

与 `scratch.py`（闯关挑战）同属 Scratch 模块但职责不同：
- 闯关：挑战 → 项目（一人一挑战一份）→ 版本 → 提交判定，服务端说了算；
- 本文件：自由作品（`scratch_works`）一人多份、可命名、可公开，直接在广场展出。
  闯关作品可"分享到广场"——分享时刻把当前工作副本快照成一份独立自由作品，
  之后两边各自演化（内容寻址共享字节，不复制存储）。

## 四条红线（与 scratch.py 同口径）

1. **归属唯一实现**。所有 /works 端点先按 `student_id` 校验归属，**别人的作品
   一律 404 而不是 403**（403 等于确认"这个 id 存在只是不属于你"，可枚举全站
   作品数，与 scratch.py `_load_own_project` 同一条口径）。
2. **公开只认 `is_public`**。画廊三个端点全部 `WHERE is_public = True`，私密作品
   在画廊里按 404 处理（"不存在"而非"有但你无权看"）。视图计数 `views` 在详情
   接口用 UPDATE 表达式递增，避免读-改-写丢更新。
3. **保存只信服务端**。与闯关保存同一条链路：先归属、再限流、最后才读文件体；
   `inspect_sb3` 结构检查 + 内容寻址落盘复用 `scratch_sb3`，不在本文件另写一份。
4. **分享是快照不是引用**。`source="challenge"` 的作品复制当时的 `sb3_key` 与
   结构摘要，之后学生在广场副本上的编辑**不会**回流到闯关工作副本，反之亦然。
   分享幂等：同一闯关作品重复分享返回已有那条（`already_shared: true`），
   不产生第二份。

## 端点

    POST   /api/scratch/works                  {title?,is_public?}  新建自由作品（默认私密）
    GET    /api/scratch/works                                         我的作品列表
    GET    /api/scratch/works/{id}                                    编辑上下文（本人）
    PUT    /api/scratch/works/{id}             multipart(file)       保存当前版本
    GET    /api/scratch/works/{id}/content.sb3                        取回内容（本人）
    PATCH  /api/scratch/works/{id}             {title?,description?,is_public?}  更新元数据
    DELETE /api/scratch/works/{id}                                    删除
    POST   /api/scratch/works/share            {project_id}          闯关作品 → 广场快照

    GET    /api/scratch/gallery                ?page=&size=&sort=&keyword=  公开作品分页
    GET    /api/scratch/gallery/{id}                                     公开作品详情（views+1）
    GET    /api/scratch/gallery/{id}/content.sb3                         公开作品内容
"""
from __future__ import annotations

import hashlib
import html
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import ScratchChallenge, ScratchProject, ScratchProjectRevision, ScratchWork, User
from ..scratch_sb3 import Sb3Invalid, inspect_sb3, read_sb3, store_sb3
from ..security import as_utc
from .auth_secure import audit, client_ip, current_user, db_session, limit, require_csrf

router = APIRouter(prefix="/api/scratch", tags=["student-scratch-works"])

SB3_MEDIA_TYPE = "application/x.scratch.sb3"

TITLE_MAX = 120
DESC_MAX = 500
GALLERY_PAGE_SIZE_MAX = 50
GALLERY_DEFAULT_PAGE_SIZE = 20


# ---------- 请求模型 ----------


class WorkCreate(BaseModel):
    title: str = Field(default="未命名作品", min_length=1, max_length=TITLE_MAX)
    # 新建与上传是两次 HTTP 请求。默认私密可确保上传失败时空草稿不会出现在广场；
    # 显式选择公开的客户端则应在创建请求里一并传入，避免再靠后续 PATCH 修正。
    is_public: bool = False


class WorkPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    description: str | None = Field(default=None, max_length=DESC_MAX)
    is_public: bool | None = None


class WorkShare(BaseModel):
    project_id: int


# ---------- 公共辅助 ----------


def _work_payload(work: ScratchWork, *, mine: bool, author: User | None = None,
                  with_content_url: bool = True, cover_base: str = "/api/scratch/works") -> dict:
    """自由作品的对外形状。mine=True 时带 `content_url`（私密作品只有本人才有取回路径）。"""
    payload: dict = {
        "id": work.id,
        "title": work.title,
        "description": work.description,
        "source": work.source,
        "source_challenge_id": work.source_challenge_id,
        "is_public": work.is_public,
        "sprite_count": work.sprite_count,
        "size_bytes": work.size_bytes,
        "views": work.views,
        # 过 as_utc：SQLite 读出为 naive，直接 isoformat 丢时区，前端相对时间会差一个时区偏移
        "created_at": as_utc(work.created_at).isoformat() if work.created_at else None,
        "updated_at": as_utc(work.updated_at).isoformat() if work.updated_at else None,
        "has_content": bool(work.sb3_key),
        # Scratch VM does not expose a server-side thumbnail, so expose a stable
        # generated cover rather than making clients guess a missing field.
        "thumbnail_url": f"{cover_base}/{work.id}/cover.svg",
    }
    if author is not None:
        payload["author"] = {"id": author.id, "username": author.username}
    if mine:
        payload["content_url"] = (f"/api/scratch/works/{work.id}/content.sb3"
                                  if work.sb3_key else None)
    return payload


def _own_work(db: Session, request: Request, work_id: int) -> tuple[User, ScratchWork]:
    """取本人自由作品。别人的作品一律 404（口径见文件头红线 1）。"""
    user = current_user(request, db)
    work = db.get(ScratchWork, work_id)
    if work is None or work.student_id != user.id:
        raise HTTPException(404, "作品不存在。")
    return user, work


def _cover_svg(work: ScratchWork) -> str:
    title = html.escape((work.title or "未命名作品")[:32])
    # A compact, deterministic cover that works before and after an .sb3 upload.
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 300">
<rect width="480" height="300" fill="#f6f7fb"/>
<rect x="24" y="24" width="432" height="252" rx="18" fill="#ffffff" stroke="#d9deea"/>
<rect x="48" y="52" width="384" height="164" rx="10" fill="#e8f4ff"/>
<circle cx="128" cy="134" r="42" fill="#ffbf00"/>
<circle cx="112" cy="126" r="5" fill="#273142"/><circle cx="144" cy="126" r="5" fill="#273142"/>
<path d="M112 148c10 9 22 9 32 0" fill="none" stroke="#273142" stroke-width="5" stroke-linecap="round"/>
<rect x="202" y="100" width="172" height="14" rx="7" fill="#5b6ee1" opacity=".9"/>
<rect x="202" y="128" width="132" height="12" rx="6" fill="#b9c4df"/>
<rect x="202" y="153" width="96" height="12" rx="6" fill="#b9c4df"/>
<text x="48" y="246" font-family="Arial,sans-serif" font-size="20" font-weight="700" fill="#273142">{title}</text>
</svg>'''


def _cover_response(work: ScratchWork) -> Response:
    return Response(content=_cover_svg(work), media_type="image/svg+xml",
                    headers={"Cache-Control": "private, max-age=60"})


def _save_bytes(work: ScratchWork, raw: bytes, settings) -> None:
    """结构检查 + 内容寻址落盘 + 回填摘要。复用闯关同一条安全闸。"""
    try:
        summary = inspect_sb3(raw, settings)
        sb3_key, digest = store_sb3(raw, settings)
    except Sb3Invalid as exc:
        raise HTTPException(400, exc.message) from exc
    work.sb3_key = sb3_key
    work.sha256 = digest
    work.size_bytes = len(raw)
    work.sprite_count = summary.sprite_count
    work.extensions_json = json.dumps(summary.extensions, ensure_ascii=False)


# ---------- 我的作品 ----------


@router.post("/works", status_code=201)
def create_work(payload: WorkCreate, request: Request, db: Session = Depends(db_session)):
    """新建一份空白自由作品（Studio 以 `?mode=free&work_id=N` 打开它）。

    只建行不建内容：学生还没保存任何 .sb3 时 `sb3_key` 为 null，Studio 装载
    分支照"没有内容"处理（与闯关"还没保存过"同口径）。
    """
    require_csrf(request)
    user = current_user(request, db)
    work = ScratchWork(student_id=user.id, title=payload.title.strip() or "未命名作品",
                       is_public=payload.is_public)
    db.add(work)
    db.commit()
    db.refresh(work)
    return _work_payload(work, mine=True)


@router.get("/works")
def list_works(request: Request, db: Session = Depends(db_session)):
    """我的作品列表（自由创作 + 从挑战分享来的），最新在前的完整清单。

    画廊是分页的公开视图，这里是本人全量视图：不分页，作品数就是学生的创作量。
    """
    user = current_user(request, db)
    rows = db.scalars(
        select(ScratchWork)
        .where(ScratchWork.student_id == user.id)
        .order_by(ScratchWork.updated_at.desc(), ScratchWork.id.desc())
    ).all()
    return {"items": [_work_payload(w, mine=True) for w in rows]}


@router.get("/works/{work_id}")
def work_detail(work_id: int, request: Request, db: Session = Depends(db_session)):
    """编辑上下文：作品 + 保存上限（Studio free 模式消费，形状对齐闯关的 project 段）。"""
    user, work = _own_work(db, request, work_id)
    settings = request.app.state.settings
    payload = _work_payload(work, mine=True)
    payload["limits"] = {
        "max_bytes": settings.scratch_sb3_max_bytes,
        "save_rate_max": settings.scratch_save_rate_max,
        "save_rate_seconds": settings.scratch_save_rate_seconds,
    }
    return payload


@router.put("/works/{work_id}")
async def save_work(work_id: int, request: Request,
                    file: UploadFile = File(...),
                    source: str = Form(default="autosave"),
                    db: Session = Depends(db_session)):
    """保存当前版本（multipart `file` = .sb3）。与闯关保存同一条校验顺序：
    先归属、再限流、最后才读文件体——反过来先读 10MB 再判权限，等于给任何
    登录用户开一条免费的带宽/磁盘消耗通道。
    """
    require_csrf(request)
    _user, work = _own_work(db, request, work_id)
    settings = request.app.state.settings
    limit(request, "scratch-save", f"{work.student_id}:work{work.id}",
          settings.scratch_save_rate_max, settings.scratch_save_rate_seconds)

    raw = await file.read(settings.scratch_sb3_max_bytes + 1)
    if len(raw) > settings.scratch_sb3_max_bytes:
        raise HTTPException(413, f"作品文件不能超过 {settings.scratch_sb3_max_bytes // (1024 * 1024)} MB。")
    changed = work.sha256 is None or work.sha256 != hashlib.sha256(raw).hexdigest()
    _save_bytes(work, raw, settings)
    db.commit()
    db.refresh(work)
    return {"work_id": work.id, "unchanged": not changed,
            "saved_at": work.updated_at.isoformat() if work.updated_at else None}


@router.get("/works/{work_id}/content.sb3")
def work_content(work_id: int, request: Request, db: Session = Depends(db_session)):
    """取回本人作品的当前版本（Studio 续做时加载）。每次都校验归属。"""
    _user, work = _own_work(db, request, work_id)
    if not work.sb3_key:
        raise HTTPException(404, "还没有保存过作品。")
    data = read_sb3(work.sb3_key, request.app.state.settings)
    if data is None:
        raise HTTPException(404, "作品文件丢失，请重新保存。")
    return Response(
        content=data, media_type=SB3_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="work-{work.id}.sb3"',
                 "Cache-Control": "private, no-store"},
    )


@router.get("/works/{work_id}/cover.svg")
def work_cover(work_id: int, request: Request, db: Session = Depends(db_session)):
    _user, work = _own_work(db, request, work_id)
    return _cover_response(work)


@router.patch("/works/{work_id}")
def patch_work(work_id: int, payload: WorkPatch, request: Request,
               db: Session = Depends(db_session)):
    """更新元数据：标题 / 简介 / 公开开关。只更新请求里带了的字段。"""
    require_csrf(request)
    _user, work = _own_work(db, request, work_id)
    if payload.title is not None:
        work.title = payload.title.strip() or "未命名作品"
    if payload.description is not None:
        work.description = payload.description.strip()
    if payload.is_public is not None:
        work.is_public = payload.is_public
    db.commit()
    db.refresh(work)
    return _work_payload(work, mine=True)


@router.delete("/works/{work_id}", status_code=204)
def delete_work(work_id: int, request: Request, db: Session = Depends(db_session)):
    """删除作品（只删行，不删内容寻址文件——同一份字节可能被别处引用，见 scratch_sb3 头注）。"""
    require_csrf(request)
    _user, work = _own_work(db, request, work_id)
    db.delete(work)
    db.commit()


@router.post("/works/share")
def share_project(payload: WorkShare, request: Request, db: Session = Depends(db_session)):
    """把闯关工作副本的**当前版本**发布为一份自由作品（广场快照）。

    幂等：同一闯关作品已分享过时返回已有那条（`already_shared: true`），
    不产生第二份，避免广场被同一作品刷屏。

    刻意不重跑课时门控（与 scratch.py 的 `_load_own_project` 不同）：分享不是
    "继续做题"，没有解锁风险——只是把已存在的内容发布为独立作品。但归属校验
    是同一道（别人的 project 404）。
    """
    require_csrf(request)
    user = current_user(request, db)
    project = db.get(ScratchProject, payload.project_id)
    if project is None or project.student_id != user.id:
        raise HTTPException(404, "作品不存在。")

    existing = db.scalar(
        select(ScratchWork).where(
            ScratchWork.student_id == user.id,
            ScratchWork.source == "challenge",
            ScratchWork.source_project_id == project.id,
        ).limit(1)
    )
    if existing is not None:
        return {**_work_payload(existing, mine=True), "already_shared": True}

    revision = db.scalar(
        select(ScratchProjectRevision).where(
            ScratchProjectRevision.project_id == project.id,
            ScratchProjectRevision.revision_no == project.current_revision_no,
        )
    )
    if revision is None or not revision.sb3_key:
        raise HTTPException(400, "请先保存作品，再分享到广场。")
    challenge = db.get(ScratchChallenge, project.challenge_id)

    work = ScratchWork(
        student_id=user.id,
        title=(challenge.title if challenge else "我的作品"),
        source="challenge",
        source_project_id=project.id,
        source_challenge_id=project.challenge_id,
        sb3_key=revision.sb3_key,
        sha256=revision.sha256,
        size_bytes=revision.size_bytes,
        sprite_count=revision.sprite_count,
        extensions_json=revision.extensions_json,
        is_public=True,
    )
    db.add(work)
    db.flush()  # 先拿到 work.id 再写审计，避免为审计多提交一次
    # 分享 = 对外发布：出不当内容时要追溯谁在何时公开了什么。
    # 只记 id 与可见范围，**不记作品内容**（《55》§8 裁定归 collab）。
    audit(db, request.app.state.settings, "work_share", "success",
          client_ip(request), user.id,
          resource_type="scratch_work", resource_id=work.id,
          summary={"schema_version": 1, "work_id": work.id,
                   "source_challenge_id": work.source_challenge_id,
                   "is_public": work.is_public})
    db.commit()
    db.refresh(work)
    return {**_work_payload(work, mine=True), "already_shared": False}


# ---------- 画廊（公开作品） ----------


def _gallery_visible(db: Session, work_id: int) -> ScratchWork:
    """画廊按 id 取公开作品。私密作品与不存在同口径：404。"""
    work = db.get(ScratchWork, work_id)
    if work is None or not work.is_public:
        raise HTTPException(404, "该作品未公开或不存在。")
    return work


@router.get("/gallery")
def gallery(request: Request, db: Session = Depends(db_session),
            page: int = 1, size: int = GALLERY_DEFAULT_PAGE_SIZE,
            sort: str = "latest", keyword: str | None = None):
    """公开作品分页浏览（首页 / 探索页消费）。

    sort=latest 按**创建时间**倒序（最新创作的作品排前，编辑不改变排序——
    否则"改过一笔"的旧作品会反复上浮，首页最新区就永远是最老一批）；sort=popular
    按浏览数倒序（最热）。keyword 对标题做包含匹配（LIKE），两端通配。
    """
    current_user(request, db)  # 画廊需要登录：学生作品不是匿名公开资源
    if page < 1:
        page = 1
    size = max(1, min(size, GALLERY_PAGE_SIZE_MAX))
    query = select(ScratchWork).where(ScratchWork.is_public.is_(True))
    count_query = select(func.count()).select_from(ScratchWork).where(
        ScratchWork.is_public.is_(True))
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        query = query.where(ScratchWork.title.like(pattern))
        count_query = count_query.where(ScratchWork.title.like(pattern))
    order = (ScratchWork.views.desc(), ScratchWork.id.desc()) if sort == "popular" \
        else (ScratchWork.created_at.desc(), ScratchWork.id.desc())
    query = query.order_by(*order).offset((page - 1) * size).limit(size)
    rows = db.scalars(query).all()
    total = db.scalar(count_query) or 0

    authors: dict[int, User] = {}
    user_ids = {r.student_id for r in rows}
    if user_ids:
        for u in db.scalars(select(User).where(User.id.in_(user_ids))):
            authors[u.id] = u
    return {
        "total": total,
        "page": page,
        "page_size": size,
        "items": [_work_payload(w, mine=False, author=authors.get(w.student_id),
                                 cover_base="/api/scratch/gallery") for w in rows],
    }


@router.get("/gallery/{work_id}")
def gallery_detail(work_id: int, request: Request, db: Session = Depends(db_session)):
    """公开作品详情。打开一次 views + 1（UPDATE 表达式递增，防并发丢更新）。"""
    user = current_user(request, db)
    work = _gallery_visible(db, work_id)
    db.execute(update(ScratchWork).where(ScratchWork.id == work.id)
               .values(views=ScratchWork.views + 1))
    db.commit()
    db.refresh(work)
    author = db.get(User, work.student_id)
    payload = _work_payload(work, mine=False, author=author, cover_base="/api/scratch/gallery")
    payload["mine"] = work.student_id == user.id
    return payload


@router.get("/gallery/{work_id}/content.sb3")
def gallery_content(work_id: int, request: Request, db: Session = Depends(db_session)):
    """公开作品内容下发（预览播放 / 下载）。只认 `is_public`，key 不是权限凭证。"""
    current_user(request, db)
    work = _gallery_visible(db, work_id)
    if not work.sb3_key:
        raise HTTPException(404, "该作品还没有内容。")
    data = read_sb3(work.sb3_key, request.app.state.settings)
    if data is None:
        raise HTTPException(404, "作品文件丢失。")
    return Response(
        content=data, media_type=SB3_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="work-{work.id}.sb3"',
                 "Cache-Control": "private, no-store"},
    )


@router.get("/gallery/{work_id}/cover.svg")
def gallery_cover(work_id: int, request: Request, db: Session = Depends(db_session)):
    current_user(request, db)
    work = _gallery_visible(db, work_id)
    return _cover_response(work)
