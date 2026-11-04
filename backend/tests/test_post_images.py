"""커뮤니티 글 사진: 운영팀만 넣고, 사이트에 배포한 파일만, 출처 표시 정보 필수."""

from __future__ import annotations

import pytest

from tests.test_members import admin_login, client, signup, use  # noqa: F401 - client 픽스처


def image(**kw) -> dict:
    img = {"src": "/community-images/degu-1.webp", "alt": "모래 위에 앉은 데구", "width": 1200, "height": 800,
           "credit": "Jane Doe", "license": "CC BY-SA 4.0",
           "source_url": "https://commons.wikimedia.org/wiki/File:Degu.jpg"}
    img.update(kw)
    return img


def test_admin_post_images_and_thumbnail(client):
    admin_login(client)
    r = client.post("/community/posts", json={"title": "[가이드] 데구", "body": "본문", "images": [image()]})
    assert r.status_code == 201, r.text
    post = r.json()
    assert post["images"] == [image()]
    listed = client.get("/community/posts").json()["items"][0]
    assert listed["thumbnail"] == image()

    # 제목만 바꾸면 사진은 그대로
    r = client.patch(f"/community/posts/{post['id']}", json={"title": "데구 가이드"})
    assert r.status_code == 200 and r.json()["images"] == [image()]
    # 사진 바꾸기·모두 빼기
    two = [image(src="/community-images/degu-2.webp"), image()]
    assert client.patch(f"/community/posts/{post['id']}", json={"images": two}).json()["images"] == two
    r = client.patch(f"/community/posts/{post['id']}", json={"images": []})
    assert r.status_code == 200 and r.json()["images"] == []
    assert client.get("/community/posts").json()["items"][0]["thumbnail"] is None


def test_members_cannot_add_images(client):
    signup(client, "user_a")
    r = client.post("/community/posts", json={"title": "제목", "body": "본문", "images": [image()]})
    assert r.status_code == 403
    r = client.post("/community/posts", json={"title": "제목", "body": "본문"})
    assert r.status_code == 201 and r.json()["images"] == []
    pid = r.json()["id"]
    assert client.patch(f"/community/posts/{pid}", json={"images": [image()]}).status_code == 403
    # 빈 목록은 바꾸는 것이 없으니 괜찮다
    assert client.patch(f"/community/posts/{pid}", json={"images": []}).status_code == 200


@pytest.mark.parametrize("bad", [
    {"src": "https://evil.example/x.jpg"},
    {"src": "/community-images/../secret.webp"},
    {"src": "/community-images/Degu.webp"},
    {"src": "/community-images/degu.gif"},
    {"source_url": "http://commons.wikimedia.org/x"},
    {"source_url": "javascript:alert(1)"},
    {"alt": ""},
    {"credit": "두\n줄"},
    {"width": 0},
    {"extra": "x"},
])
def test_image_validation(client, bad):
    admin_login(client)
    r = client.post("/community/posts", json={"title": "제목", "body": "본문", "images": [image(**bad)]})
    assert r.status_code == 422


def test_image_count_limit(client):
    admin_login(client)
    imgs = [image(src=f"/community-images/p-{i}.webp") for i in range(5)]
    assert client.post("/community/posts", json={"title": "제목", "body": "본문", "images": imgs}).status_code == 422
    assert client.post("/community/posts", json={"title": "제목", "body": "본문", "images": imgs[:4]}).status_code == 201
