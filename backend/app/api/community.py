"""커뮤니티: 글·댓글. 읽기는 누구나, 쓰기는 회원만. 글에 내 설계를 첨부하면 그 설계가 공유된다."""

from __future__ import annotations

from fastapi import Depends, Query, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, get_service, make_router
from app.auth import get_current_user, get_optional_user, get_verified_user
from app.errors import ForbiddenError
from app.models import Comment, DesignVersion, MarketItem, Post, User
from app.schemas import (
    ID_RE,
    AuthorOut,
    CommentIn,
    CommentOut,
    MarketItemBrief,
    PostImage,
    PostIn,
    PostListOut,
    PostOut,
    PostSummary,
    PostUpdateIn,
    SharedDesignOut,
)
from app.services import usage
from app.services.design_service import DesignService, NotFoundError

router = make_router(prefix="/community", tags=["커뮤니티"])

EXCERPT_LEN = 140
COMMENTS_SHOWN = 200  # 글 보기에 담는 최근 댓글 수 (응답이 끝없이 커지지 않게. 댓글 쓰기는 막지 않는다)
MAX_PAGE = 1000


def _author(u: User) -> AuthorOut:
    return AuthorOut(nickname=u.nickname, role=u.role)


def _can_manage(user: User | None, author_id: str) -> bool:
    return user is not None and (user.is_admin or user.id == author_id)


def _get_post(db: Session, post_id: str) -> Post:
    post = None
    if ID_RE.fullmatch(post_id):
        post = db.scalar(select(Post).where(Post.id == post_id).options(selectinload(Post.author)))
    if post is None:
        raise NotFoundError("글을 찾을 수 없습니다.")
    return post


def _recent_comments(db: Session, post_id: str) -> tuple[list[Comment], int]:
    """최근 댓글 COMMENTS_SHOWN 개(오래된 것부터)와 전체 댓글 수."""
    total = db.scalar(select(func.count(Comment.id)).where(Comment.post_id == post_id)) or 0
    latest = db.scalars(
        select(Comment).where(Comment.post_id == post_id).options(selectinload(Comment.author))
        .order_by(Comment.created_at.desc(), Comment.id.desc()).limit(COMMENTS_SHOWN)
    ).all()
    return list(reversed(latest)), total


def _images(post: Post) -> list[PostImage]:
    return [PostImage(**i) for i in post.images or []]


def _check_images(images: list[PostImage] | None, user: User) -> None:
    # 회원 사진 올리기는 아직 없다: 사이트에 함께 배포한 사진(출처 표시 포함)을 운영팀 글에만 넣는다
    if images and not user.is_admin:
        raise ForbiddenError("사진은 운영팀 글에만 넣을 수 있어요.")


def _market_brief(db: Session, post: Post) -> MarketItemBrief | None:
    """이 글이 공유 작품 소개 글이면 그 작품 요약"""
    item = db.scalar(select(MarketItem).where(MarketItem.post_id == post.id).options(selectinload(MarketItem.files)))
    if item is None:
        return None
    from app.api.market import _file_out, _formats, _image  # 순환 import 방지

    img = _image(item)
    return MarketItemBrief(id=item.id, title=item.title, formats=_formats(item), image=_file_out(img) if img else None)


def _post_out(db: Session, svc: DesignService, post: Post, user: User | None) -> PostOut:
    comments, total = _recent_comments(db, post.id)
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
        created_at=post.created_at, updated_at=post.updated_at, design=shared, images=_images(post),
        market_item=_market_brief(db, post),
        comments=[CommentOut(id=c.id, body=c.body, author=_author(c.author), created_at=c.created_at,
                             can_delete=_can_manage(user, c.author_id)) for c in comments],
        comment_total=total,
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
    # 공유 작품 소개 글 (이 페이지의 글만)
    market_ids: dict[str, str] = {}
    if posts:
        market_ids = dict(db.execute(select(MarketItem.post_id, MarketItem.id)
                                     .where(MarketItem.post_id.in_([p.id for p in posts]))).all())
    items = [
        PostSummary(
            id=p.id, title=p.title,
            excerpt=(p.body[:EXCERPT_LEN] + "…") if len(p.body) > EXCERPT_LEN else p.body,
            author=_author(p.author), created_at=p.created_at, comment_count=counts.get(p.id, 0),
            has_design=p.design_id is not None, thumbnail=(_images(p) or [None])[0],
            market_item_id=market_ids.get(p.id),
        )
        for p in posts
    ]
    return PostListOut(items=items, total=total, page=page, page_size=page_size)


@router.post("/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED, summary="글쓰기 (설계 첨부 가능)")
def create_post(data: PostIn, request: Request, db: Session = Depends(get_db),
                svc: DesignService = Depends(get_service), user: User = Depends(get_verified_user)):
    _check_images(data.images, user)
    version = None
    if data.design_id is not None:
        design = svc.get_editable_design(db, data.design_id, user)  # 내 설계만 공유할 수 있다
        version = svc.get_version(db, design, data.design_version).version  # 이 버전만 공개된다
    limit = request.app.state.settings.post_daily_limit
    # 지운 글·댓글도 센다 (지우고 다시 써서 피하지 못하게)
    usage.reserve_per_member(db, "post", user, limit, f"글은 24시간에 {limit}개까지 쓸 수 있어요.", "too_many_posts")
    post = Post(author_id=user.id, title=data.title, body=data.body, design_id=data.design_id,
                design_version=version, images=[i.model_dump() for i in data.images] or None)
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
    if data.images is not None:
        _check_images(data.images, user)
        post.images = [i.model_dump() for i in data.images] or None
    db.commit()
    db.refresh(post)
    return _post_out(db, svc, post, user)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT, summary="글 삭제 (작성자·관리자)")
def delete_post(post_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    post = _get_post(db, post_id)
    if not _can_manage(user, post.author_id):
        raise ForbiddenError("내가 쓴 글만 지울 수 있어요.")
    # 공유 작품의 소개 글이면 연결만 끊는다 (작품은 남는다)
    db.execute(update(MarketItem).where(MarketItem.post_id == post.id).values(post_id=None))
    db.delete(post)  # 댓글도 함께 삭제. 첨부했던 설계는 다른 글에 첨부되어 있지 않으면 다시 비공개가 된다
    db.commit()
    return Response(status_code=204)


@router.post("/posts/{post_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED,
             summary="댓글 쓰기")
def create_comment(post_id: str, data: CommentIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_verified_user)):
    post = _get_post(db, post_id)
    limit = request.app.state.settings.comment_daily_limit
    usage.reserve_per_member(db, "comment", user, limit, f"댓글은 24시간에 {limit}개까지 쓸 수 있어요.",
                             "too_many_comments")
    c = Comment(post_id=post.id, author_id=user.id, body=data.body)
    db.add(c)
    db.commit()
    db.refresh(c)
    return CommentOut(id=c.id, body=c.body, author=_author(user), created_at=c.created_at, can_delete=True)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="댓글 삭제 (작성자·관리자)")
def delete_comment(comment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(Comment, comment_id) if ID_RE.fullmatch(comment_id) else None
    if c is None:
        raise NotFoundError("댓글을 찾을 수 없습니다.")
    if not _can_manage(user, c.author_id):
        raise ForbiddenError("내가 쓴 댓글만 지울 수 있어요.")
    db.delete(c)
    db.commit()
    return Response(status_code=204)
