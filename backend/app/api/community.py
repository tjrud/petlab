"""커뮤니티: 글·댓글. 읽기는 누구나, 쓰기는 회원만. 글에 내 설계를 첨부하면 그 설계가 공유된다."""

from __future__ import annotations

from fastapi import Depends, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, get_service, make_router
from app.auth import get_current_user, get_optional_user
from app.errors import ConflictError, ForbiddenError
from app.models import Comment, DesignVersion, Post, User
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
from app.services import usage
from app.services.design_service import _ID_RE, DesignService, NotFoundError

router = make_router(prefix="/community", tags=["커뮤니티"])

EXCERPT_LEN = 140
MAX_COMMENTS_PER_POST = 300  # 글 하나의 댓글 수 상한 (글 보기 응답이 끝없이 커지지 않게)
MAX_PAGE = 1000


def _author(u: User) -> AuthorOut:
    return AuthorOut(nickname=u.nickname, role=u.role)


def _can_manage(user: User | None, author_id: str) -> bool:
    return user is not None and (user.is_admin or user.id == author_id)


def _get_post(db: Session, post_id: str, with_comments: bool = False) -> Post:
    post = None
    if _ID_RE.fullmatch(post_id):
        opts = [selectinload(Post.author)]
        if with_comments:
            opts.append(selectinload(Post.comments).selectinload(Comment.author))
        post = db.scalar(select(Post).where(Post.id == post_id).options(*opts))
    if post is None:
        raise NotFoundError("글을 찾을 수 없습니다.")
    return post


def _reserve(db: Session, kind: str, user: User, limit: int, message_ko: str, code: str) -> None:
    """24시간 글·댓글 수 상한 (관리자 제외). 지운 글·댓글도 센다 (지우고 다시 써서 피하지 못하게)."""
    if not user.is_admin:
        usage.reserve(db, kind, user, per_user=usage.Cap(limit, message_ko, code))


def _post_out(db: Session, svc: DesignService, post: Post, user: User | None) -> PostOut:
    shared = None
    if post.design is not None:
        d = post.design
        # 첨부한 버전만 읽는다 (설계의 모든 버전 JSON 을 불러오지 않게)
        v = db.scalar(select(DesignVersion).where(DesignVersion.design_id == d.id,
                                                  DesignVersion.version == post.design_version))
        if v is None:
            v = db.scalar(select(DesignVersion).where(DesignVersion.design_id == d.id)
                          .order_by(DesignVersion.version.desc()).limit(1))
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
def list_posts(page: int = Query(default=1, ge=1, le=MAX_PAGE), page_size: int = Query(default=20, ge=1, le=50),
               db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Post.id))) or 0
    posts = db.scalars(
        select(Post).options(selectinload(Post.author))
        .order_by(Post.created_at.desc(), Post.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    # 댓글 수는 이 페이지의 글만 센다 (댓글 테이블 전체를 집계하지 않게)
    counts: dict[str, int] = {}
    if posts:
        counts = dict(db.execute(
            select(Comment.post_id, func.count(Comment.id))
            .where(Comment.post_id.in_([p.id for p in posts])).group_by(Comment.post_id)
        ).all())
    items = [
        PostSummary(
            id=p.id, title=p.title,
            excerpt=(p.body[:EXCERPT_LEN] + "…") if len(p.body) > EXCERPT_LEN else p.body,
            author=_author(p.author), created_at=p.created_at, comment_count=counts.get(p.id, 0),
            has_design=p.design_id is not None,
        )
        for p in posts
    ]
    return PostListOut(items=items, total=total, page=page, page_size=page_size)


@router.post("/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED, summary="글쓰기 (설계 첨부 가능)")
def create_post(data: PostIn, request: Request, db: Session = Depends(get_db),
                svc: DesignService = Depends(get_service), user: User = Depends(get_current_user)):
    version = None
    if data.design_id is not None:
        design = svc.get_editable_design(db, data.design_id, user)  # 내 설계만 공유할 수 있다
        version = svc.get_version(db, design, data.design_version).version  # 이 버전만 공개된다
    limit = request.app.state.settings.post_daily_limit
    _reserve(db, "post", user, limit, f"글은 24시간에 {limit}개까지 쓸 수 있어요.", "too_many_posts")
    post = Post(author_id=user.id, title=data.title, body=data.body, design_id=data.design_id,
                design_version=version)
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_out(db, svc, post, user)


@router.get("/posts/{post_id}", response_model=PostOut, summary="글 보기 (누구나)")
def get_post(post_id: str, db: Session = Depends(get_db), svc: DesignService = Depends(get_service),
             user: User | None = Depends(get_optional_user)):
    return _post_out(db, svc, _get_post(db, post_id, with_comments=True), user)


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
    if (db.scalar(select(func.count(Comment.id)).where(Comment.post_id == post.id)) or 0) >= MAX_COMMENTS_PER_POST:
        raise ConflictError(f"이 글에는 댓글을 더 달 수 없어요 (최대 {MAX_COMMENTS_PER_POST}개).",
                            code="comment_limit_reached")
    limit = request.app.state.settings.comment_daily_limit
    _reserve(db, "comment", user, limit, f"댓글은 24시간에 {limit}개까지 쓸 수 있어요.", "too_many_comments")
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
