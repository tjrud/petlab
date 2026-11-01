"""커뮤니티: 글·댓글. 읽기는 누구나, 쓰기는 회원만. 글에 내 설계를 첨부하면 그 설계가 공유된다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_service
from app.auth import get_current_user, get_optional_user
from app.errors import ForbiddenError, QuotaExceededError
from app.models import Comment, Post, User
from app.schemas import (
    AuthorOut,
    CommentIn,
    CommentOut,
    PostIn,
    PostListOut,
    PostOut,
    PostSummary,
    PostUpdateIn,
    SharedDesignOut,
)
from app.services.design_service import _ID_RE, DesignService, NotFoundError

router = APIRouter(prefix="/community", tags=["커뮤니티"])

EXCERPT_LEN = 140


def _author(u: User) -> AuthorOut:
    return AuthorOut(nickname=u.nickname, role=u.role)


def _can_manage(user: User | None, author_id: str) -> bool:
    return user is not None and (user.is_admin or user.id == author_id)


def _get_post(db: Session, post_id: str) -> Post:
    post = db.get(Post, post_id) if _ID_RE.fullmatch(post_id) else None
    if post is None:
        raise NotFoundError("글을 찾을 수 없습니다.")
    return post


def _recent_count(db: Session, model, author_col, user: User) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.scalar(select(func.count(model.id)).where(author_col == user.id, model.created_at >= since)) or 0


def _post_out(db: Session, svc: DesignService, post: Post, user: User | None) -> PostOut:
    shared = None
    if post.design is not None:
        d = post.design
        v = next((x for x in d.versions if x.version == post.design_version), None) or d.versions[-1]
        shared = SharedDesignOut(
            id=d.id, version=v.version, title=svc.title_of(d), summary_ko=v.llm_spec.get("summary_ko", ""),
            item_labels=[it["label_ko"] for it in v.items], passed=v.passed, habitat=svc.habitat_out(d.habitat),
        )
    return PostOut(
        id=post.id, title=post.title, body=post.body, author=_author(post.author),
        created_at=post.created_at, updated_at=post.updated_at, design=shared,
        comments=[CommentOut(id=c.id, body=c.body, author=_author(c.author), created_at=c.created_at,
                             can_delete=_can_manage(user, c.author_id)) for c in post.comments],
        can_edit=user is not None and user.id == post.author_id,
        can_delete=_can_manage(user, post.author_id),
    )


@router.get("/posts", response_model=PostListOut, summary="글 목록 (최신순, 누구나)")
def list_posts(page: int = Query(default=1, ge=1, le=10_000), page_size: int = Query(default=20, ge=1, le=50),
               db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Post.id))) or 0
    counts = (select(Comment.post_id, func.count(Comment.id).label("n")).group_by(Comment.post_id).subquery())
    rows = db.execute(
        select(Post, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.post_id == Post.id)
        .order_by(Post.created_at.desc(), Post.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [
        PostSummary(
            id=p.id, title=p.title,
            excerpt=(p.body[:EXCERPT_LEN] + "…") if len(p.body) > EXCERPT_LEN else p.body,
            author=_author(p.author), created_at=p.created_at, comment_count=n, has_design=p.design_id is not None,
        )
        for p, n in rows
    ]
    return PostListOut(items=items, total=total, page=page, page_size=page_size)


@router.post("/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED, summary="글쓰기 (설계 첨부 가능)")
def create_post(data: PostIn, request: Request, db: Session = Depends(get_db),
                svc: DesignService = Depends(get_service), user: User = Depends(get_current_user)):
    limit = request.app.state.settings.post_daily_limit
    if not user.is_admin and _recent_count(db, Post, Post.author_id, user) >= limit:
        raise QuotaExceededError(f"글은 24시간에 {limit}개까지 쓸 수 있어요.", code="too_many_posts")
    version = None
    if data.design_id is not None:
        design = svc.get_editable_design(db, data.design_id, user)  # 내 설계만 공유할 수 있다
        version = svc.get_version(db, design, data.design_version).version
    post = Post(author_id=user.id, title=data.title, body=data.body, design_id=data.design_id,
                design_version=version)
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_out(db, svc, post, user)


@router.get("/posts/{post_id}", response_model=PostOut, summary="글 보기 (누구나)")
def get_post(post_id: str, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
             user: User | None = Depends(get_optional_user)):
    return _post_out(db, svc, _get_post(db, post_id), user)


@router.patch("/posts/{post_id}", response_model=PostOut, summary="글 수정 (작성자만)")
def update_post(post_id: str, data: PostUpdateIn, db: Session = Depends(get_db),
                svc: DesignService = Depends(get_service), user: User = Depends(get_current_user)):
    post = _get_post(db, post_id)
    if post.author_id != user.id:
        raise ForbiddenError("내가 쓴 글만 고칠 수 있어요.")
    if data.title is not None:
        post.title = data.title
    if data.body is not None:
        post.body = data.body
    db.commit()
    db.refresh(post)
    return _post_out(db, svc, post, user)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT, summary="글 삭제 (작성자·관리자)")
def delete_post(post_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    post = _get_post(db, post_id)
    if not _can_manage(user, post.author_id):
        raise ForbiddenError("내가 쓴 글만 지울 수 있어요.")
    db.delete(post)  # 댓글도 함께 삭제. 첨부했던 설계는 다른 글에 첨부되어 있지 않으면 다시 비공개가 된다
    db.commit()
    return Response(status_code=204)


@router.post("/posts/{post_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED,
             summary="댓글 쓰기")
def create_comment(post_id: str, data: CommentIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    post = _get_post(db, post_id)
    limit = request.app.state.settings.comment_daily_limit
    if not user.is_admin and _recent_count(db, Comment, Comment.author_id, user) >= limit:
        raise QuotaExceededError(f"댓글은 24시간에 {limit}개까지 쓸 수 있어요.", code="too_many_comments")
    c = Comment(post_id=post.id, author_id=user.id, body=data.body)
    db.add(c)
    db.commit()
    db.refresh(c)
    return CommentOut(id=c.id, body=c.body, author=_author(user), created_at=c.created_at, can_delete=True)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="댓글 삭제 (작성자·관리자)")
def delete_comment(comment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(Comment, comment_id) if _ID_RE.fullmatch(comment_id) else None
    if c is None:
        raise NotFoundError("댓글을 찾을 수 없습니다.")
    if not _can_manage(user, c.author_id):
        raise ForbiddenError("내가 쓴 댓글만 지울 수 있어요.")
    db.delete(c)
    db.commit()
    return Response(status_code=204)
