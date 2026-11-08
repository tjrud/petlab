"""탐색: 조각 업로드·내용 확인·작품 올리기·커뮤니티 소개 글·설계 공유·권한·저장소."""

from __future__ import annotations

import io
import os
import struct
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.storage import BlobStorage
from tests.test_members import admin_login, make_design, settings, signup, use

CHUNK = 3 * 1024 * 1024


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path, market_storage_dir=tmp_path / "market"))) as c:
        yield c


def skp_bytes(size: int = 7 * 1024 * 1024 + 123) -> bytes:
    head = b"\xff\xfe\xff\x0e" + "SketchUp Model".encode("utf-16le") + b"\xff\xfe\xff\x08" + "{17.0.1}".encode("utf-16le")
    return head + os.urandom(size - len(head))


def threemf_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("3D/3dmodel.model", "<model/>")
    return buf.getvalue()


def stl_bytes() -> bytes:
    tri = struct.pack("<12fH", *([0.0] * 3 + [0, 0, 0] + [1, 0, 0] + [0, 1, 0]), 0)
    return b"\x00" * 80 + struct.pack("<I", 2) + tri * 2


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def upload(c: TestClient, filename: str, data: bytes, kind: str = "model", status: int = 200) -> dict:
    r = c.post("/market/uploads", json={"filename": filename, "size": len(data), "kind": kind})
    assert r.status_code == 201, r.text
    up = r.json()
    assert up["chunk_bytes"] == CHUNK and up["chunks"] == -(-len(data) // CHUNK)
    for n in range(up["chunks"]):
        r = c.put(f"/market/uploads/{up['id']}/chunks/{n}", content=data[n * CHUNK:(n + 1) * CHUNK])
        assert r.status_code == 204, r.text
    r = c.post(f"/market/uploads/{up['id']}/complete")
    assert r.status_code == status, r.text
    return r.json()


def item_body(**kw) -> dict:
    b = {"title": "나무 은신처 (다방형)", "description": "SketchUp 2017로 만든 다방 은신처예요.", "category": "hideout"}
    b.update(kw)
    return b


def test_upload_item_community_post_and_download(client):
    signup(client, "maker_a")
    data = skp_bytes()
    f = upload(client, "은신처.skp", data)
    assert f["format"] == "skp" and f["size"] == len(data) and f["kind"] == "model"
    img = upload(client, "preview.png", PNG, kind="image")
    tri = upload(client, "part.stl", stl_bytes())
    mf = upload(client, "plate.3mf", threemf_bytes())

    r = client.post("/market/items", json=item_body(file_ids=[f["id"], tri["id"], mf["id"]], image_file_id=img["id"]))
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["formats"] == ["3mf", "skp", "stl"] and item["image"]["id"] == img["id"]
    assert [x["filename"] for x in item["files"]] == ["은신처.skp", "part.stl", "plate.3mf"]
    assert item["category_name_ko"] == "은신처" and item["can_edit"] and item["post_id"]

    # 커뮤니티 소개 글: 제목 앞에 [탐색], 글에 작품 요약
    post = client.get(f"/community/posts/{item['post_id']}").json()
    assert post["title"] == "[탐색] 나무 은신처 (다방형)" and post["market_item"]["id"] == item["id"]
    listed = client.get("/community/posts").json()["items"][0]
    assert listed["market_item_id"] == item["id"]

    # 누구나 목록·작품·내려받기 (로컬 저장소는 백엔드가 파일을 돌려준다)
    use(client, None)
    lst = client.get("/market/items").json()
    assert lst["total"] == 1 and lst["items"][0]["image"]["view_url"].endswith("/view")
    assert client.get("/market/items?category=tunnel").json()["total"] == 0
    got = client.get(f"/market/files/{f['id']}/download")
    assert got.status_code == 200 and got.content == data
    assert "attachment" in got.headers["content-disposition"]
    assert client.get(f"/market/items/{item['id']}").json()["download_count"] == 1
    assert client.get(img["view_url"]).content == PNG


@pytest.mark.parametrize("name,data,code", [
    ("x.skp", b"not sketchup at all" * 10, "bad_file_content"),
    ("x.3mf", b"PK\x03\x04garbage", "bad_file_content"),
    ("x.stl", b"hello world", "bad_file_content"),
])
def test_content_must_match_extension(client, name, data, code):
    signup(client, "maker_a")
    r = upload(client, name, data, status=400)
    assert r["detail"]["code"] == code


def test_upload_validation(client):
    signup(client, "maker_a")
    r = client.post("/market/uploads", json={"filename": "virus.exe", "size": 10})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "unsupported_format"
    r = client.post("/market/uploads", json={"filename": "a.skp", "size": 60 * 1024 * 1024})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "file_too_large"
    r = client.post("/market/uploads", json={"filename": "a.skp", "size": 10, "kind": "image"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "unsupported_format"
    up = client.post("/market/uploads", json={"filename": "a.stl", "size": CHUNK + 5}).json()
    # 조각 크기·번호가 맞지 않으면 거절, 다 오기 전에 마치면 거절
    assert client.put(f"/market/uploads/{up['id']}/chunks/0", content=b"x" * 10).status_code == 400
    assert client.put(f"/market/uploads/{up['id']}/chunks/5", content=b"x" * 5).status_code == 400
    assert client.put(f"/market/uploads/{up['id']}/chunks/1", content=b"x" * 5).status_code == 204
    r = client.post(f"/market/uploads/{up['id']}/complete")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "upload_incomplete"
    assert client.post("/market/items", json=item_body()).json()["detail"]["code"] == "empty_item"


def test_permissions(client):
    a = signup(client, "maker_a")
    f = upload(client, "a.stl", stl_bytes())
    pending = client.post("/market/uploads", json={"filename": "b.stl", "size": 100}).json()

    b = signup(client, "maker_b")
    use(client, b)
    # 남의 파일·업로드는 쓸 수 없고, 작품에 붙기 전 파일은 내려받을 수 없다
    assert client.post("/market/items", json=item_body(file_ids=[f["id"]])).status_code == 404
    assert client.put(f"/market/uploads/{pending['id']}/chunks/0", content=b"x" * 100).status_code == 404
    assert client.get(f"/market/files/{f['id']}/download").status_code == 404

    use(client, a)
    item = client.post("/market/items", json=item_body(file_ids=[f["id"]], post_to_community=False)).json()
    assert item["post_id"] is None
    # 한 파일은 한 작품에만
    assert client.post("/market/items", json=item_body(file_ids=[f["id"]])).status_code == 404

    use(client, b)
    assert client.patch(f"/market/items/{item['id']}", json={"title": "x"}).status_code == 403
    assert client.delete(f"/market/items/{item['id']}").status_code == 403
    use(client, a)
    r = client.patch(f"/market/items/{item['id']}", json={"title": "바꾼 제목", "category": "tunnel"})
    assert r.status_code == 200 and r.json()["title"] == "바꾼 제목" and r.json()["category"] == "tunnel"

    # 관리자는 지울 수 있고, 파일도 함께 사라진다
    admin_login(client)
    assert client.delete(f"/market/items/{item['id']}").status_code == 204
    assert client.get(f"/market/items/{item['id']}").status_code == 404
    assert client.get(f"/market/files/{f['id']}/download").status_code == 404

    use(client, None)
    assert client.post("/market/uploads", json={"filename": "a.stl", "size": 10}).status_code == 401
    assert client.post("/market/items", json=item_body()).status_code == 401


def test_design_attached_through_community_post(client):
    a = signup(client, "maker_a")
    d = make_design(client)
    item = client.post("/market/items", json=item_body(design_id=d["id"], post_to_community=False)).json()
    # 설계를 붙이면 소개 글을 꼭 함께 올린다 (그 글로 설계 버전이 공개된다)
    assert item["post_id"] and item["formats"] == ["nestforge"] and item["design"]["id"] == d["id"]

    b = signup(client, "maker_b")
    use(client, b)
    seen = client.get(f"/market/items/{item['id']}").json()
    assert seen["design"]["version"] == 1 and not seen["can_edit"]
    assert client.get(f"/designs/{d['id']}/export?format=stl&version=1").status_code in (200, 409)
    # 남의 설계는 붙일 수 없다
    assert client.post("/market/items", json=item_body(design_id=d["id"])).status_code == 404

    # 소개 글을 지우면 작품은 남고, 설계 공개가 끝나 설계 카드도 사라진다
    use(client, a)
    assert client.delete(f"/community/posts/{item['post_id']}").status_code == 204
    after = client.get(f"/market/items/{item['id']}").json()
    assert after["post_id"] is None and after["design"] is None


def test_storage_unavailable_on_deploy_without_blob_token(tmp_path):
    s = settings(tmp_path, api_prefix="/api", market_storage_dir=tmp_path / "market")
    with TestClient(create_app(s)) as c:
        assert c.get("/api/market/config").json()["uploads_enabled"] is False
        signup_path = c.post("/api/auth/signup", json={"username": "maker_a", "nickname": "메이커", "password": "hamster-love-123"})
        assert signup_path.status_code == 201
        r = c.post("/api/market/uploads", json={"filename": "a.skp", "size": 10})
        assert r.status_code == 503 and r.json()["detail"]["code"] == "storage_unavailable"
        assert c.get("/api/market/items").json()["total"] == 0  # 보기는 된다


def test_blob_storage_requests(monkeypatch):
    calls = []

    def fake_put(url, params, content, headers, timeout):
        calls.append(("put", url, params, headers, len(content)))
        return httpx.Response(200, json={"url": f"https://abc.public.blob.vercel-storage.com/{params['pathname']}"})

    def fake_post(url, json, headers, timeout):
        calls.append(("post", url, json, headers))
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "put", fake_put)
    monkeypatch.setattr(httpx, "post", fake_post)
    st = BlobStorage("tok", "https://vercel.com/api/blob")
    out = st.put("market/abc/abc.skp", b"12345", "application/vnd.sketchup.skp")
    assert out.url == "https://abc.public.blob.vercel-storage.com/market/abc/abc.skp"
    _, url, params, headers, n = calls[0]
    assert url == "https://vercel.com/api/blob/" and params == {"pathname": "market/abc/abc.skp"} and n == 5
    assert headers["authorization"] == "Bearer tok" and headers["x-vercel-blob-access"] == "public"
    st.delete([out])
    assert calls[1][1] == "https://vercel.com/api/blob/delete" and calls[1][2] == {"urls": [out.url]}


def tetra_stl(size: float = 120.0) -> bytes:
    """크기 size×size×size 정사면체 모양 바이너리 STL"""
    v = [(0, 0, 0), (size, 0, 0), (0, size, 0), (0, 0, size)]
    faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    out = b"\x00" * 80 + struct.pack("<I", len(faces))
    for a, b, c in faces:
        out += struct.pack("<3f", 0, 0, 0) + b"".join(struct.pack("<3f", *v[i]) for i in (a, b, c)) + b"\x00\x00"
    return out


def test_mesh_dims_my_files_and_visibility(client):
    a = signup(client, "maker_a")
    f = upload(client, "house.stl", tetra_stl(120))
    assert f["dims_mm"] == [120.0, 120.0, 120.0] and f["mesh_url"].endswith("/mesh") and f["attached"] is False
    sk = upload(client, "house.skp", skp_bytes(1024))
    assert sk["dims_mm"] is None and sk["mesh_url"] is None
    mine = client.get("/market/files/mine").json()
    assert [x["id"] for x in mine] == [sk["id"], f["id"]]
    assert client.get(f["mesh_url"]).content == tetra_stl(120)
    # 남은 아직 볼 수 없다
    b = signup(client, "maker_b")
    use(client, b)
    assert client.get(f["mesh_url"]).status_code == 404
    assert client.get("/market/files/mine").json() == []
    use(client, None)
    assert client.get("/market/files/mine").status_code == 401


def test_layout_share_makes_files_visible_and_copy(client):
    a = signup(client, "maker_a")
    f = upload(client, "house.stl", tetra_stl(100))
    lay = client.post("/layouts", json={
        "name": "거실 케이지", "species": "hamster", "size": "syrian",
        "cage": {"width_mm": 1000, "depth_mm": 500, "height_mm": 500},
        "items": [{"id": "a1", "asset": "hideout_multi", "x_mm": 160, "y_mm": 390, "rotation_deg": 0},
                  {"id": "a2", "asset": f"file_{f['id']}", "x_mm": 500, "y_mm": 250, "rotation_deg": 90}],
    }).json()
    item = client.post("/market/items", json=item_body(category="layout", layout_id=lay["id"])).json()
    assert item["formats"] == ["layout"] and item["has_layout"] and item["category_name_ko"] == "가상 케이지 배치"
    assert item["layout"]["cage"]["width_mm"] == 1000 and len(item["layout"]["items"]) == 2
    assert item["layout"]["size_name_ko"]

    b = signup(client, "maker_b")
    use(client, b)
    # 배치에 들어 있는 파일은 다른 사람도 3D 로 본다
    assert client.get(f["mesh_url"]).status_code == 200
    # 남의 배치안은 공유할 수 없다
    assert client.post("/market/items", json=item_body(layout_id=lay["id"])).status_code == 404
    r = client.post(f"/market/items/{item['id']}/copy-layout")
    assert r.status_code == 201
    copied = client.get(f"/layouts/{r.json()['layout_id']}").json()
    assert copied["name"] == "거실 케이지 (탐색)" and copied["items"] == lay["items"] and copied["cage"] == lay["cage"]

    files_only = None
    use(client, a)
    files_only = client.post("/market/items", json=item_body(file_ids=[upload(client, "x.stl", tetra_stl(50))["id"]])).json()
    use(client, b)
    r = client.post(f"/market/items/{files_only['id']}/copy-layout")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "no_layout"
    use(client, None)
    assert client.post(f"/market/items/{item['id']}/copy-layout").status_code == 401


def test_recommendations(client):
    b = signup(client, "maker_b")
    tunnel = client.post("/market/items", json=item_body(title="긴 터널", category="tunnel",
                                                          file_ids=[upload(client, "t.stl", tetra_stl(60))["id"]])).json()
    hide = client.post("/market/items", json=item_body(title="다방 은신처", category="hideout",
                                                        file_ids=[upload(client, "h.stl", tetra_stl(60))["id"]])).json()

    # 로그인하지 않으면 인기·새로움 순 (까닭도 함께)
    use(client, None)
    anon = client.get("/market/recommended").json()
    assert {x["id"] for x in anon} == {tunnel["id"], hide["id"]} and all(x["reason_ko"] for x in anon)

    # 내 설계에 은신처가 있으면 은신처 작품이 먼저
    a = signup(client, "maker_a")
    make_design(client, "은신처를 왼쪽에")
    rec = client.get("/market/recommended").json()
    assert rec[0]["id"] == hide["id"] and "내 설계" in rec[0]["reason_ko"]

    # 터널 작품을 여러 번 보고 내려받으면 터널 관심도가 오른다 (본 기록은 1시간에 한 번)
    for _ in range(3):
        client.get(f"/market/items/{tunnel['id']}")
    f_id = client.get(f"/market/items/{tunnel['id']}").json()["files"][0]["id"]
    client.get(f"/market/files/{f_id}/download")
    rec = client.get("/market/recommended").json()
    assert {x["id"] for x in rec} == {tunnel["id"], hide["id"]}

    # 내 작품은 다른 사람 작품 뒤에, 그것밖에 없으면 '내가 올린 작품'으로 보여 준다 (추천이 비지 않게)
    use(client, b)
    mine = client.get("/market/recommended").json()
    assert {x["id"] for x in mine} == {tunnel["id"], hide["id"]} and all(x["reason_ko"] == "내가 올린 작품" for x in mine)
    other = client.post("/market/items", json=item_body(title="남의 다리", category="ramp",
                                                         file_ids=[upload(client, "r.stl", tetra_stl(60))["id"]])).json()
    use(client, a)
    rec = client.get("/market/recommended").json()
    assert other["id"] in [x["id"] for x in rec]
    use(client, b)
    assert [x["reason_ko"] for x in client.get("/market/recommended").json()][-2:] == ["내가 올린 작품"] * 2


def test_recommendations_put_viewable_items_first(client):
    """3D 로 보고 가상 케이지에 놓아 볼 수 있는 STL 작품이, 더 많이 내려받은 SKP 작품보다 앞에 온다"""
    signup(client, "maker_a")
    skp = client.post("/market/items", json=item_body(title="SKP 예시", category="etc",
                                                       file_ids=[upload(client, "a.skp", skp_bytes(2048))["id"]])).json()
    stl = client.post("/market/items", json=item_body(title="STL 은신처", category="hideout",
                                                       file_ids=[upload(client, "b.stl", tetra_stl(60))["id"]],
                                                       image_file_id=upload(client, "p.png", PNG, kind="image")["id"])).json()
    use(client, None)
    skp_file = client.get(f"/market/items/{skp['id']}").json()["files"][0]["id"]
    client.get(f"/market/files/{skp_file}/download", follow_redirects=False)  # SKP 가 내려받기 1회 앞선다
    rec = client.get("/market/recommended").json()
    assert [x["id"] for x in rec] == [stl["id"], skp["id"]]
    assert rec[0]["reason_ko"] == "3D로 보고 가상 케이지에 놓아 볼 수 있어요"


def test_mesh_dims_reads_ascii_stl_and_skips_zip_bombs():
    from app.market_formats import mesh_dims

    ascii_stl = (b"solid t\n facet normal 0 0 1\n  outer loop\n   vertex 0 0 0\n   vertex 40 0 0\n"
                 b"   vertex 0 25.5 10\n  endloop\n endfacet\nendsolid t\n")
    assert mesh_dims("stl", ascii_stl) == [40.0, 25.5, 10.0]
    assert mesh_dims("stl", tetra_stl(80)) == [80.0, 80.0, 80.0]
    # 작게 압축돼 있어도 풀린 크기가 크면 열지 않는다
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("3D/3dmodel.model", b"\0" * (80 * 1024 * 1024))
    assert len(buf.getvalue()) < 1024 * 1024 and mesh_dims("3mf", buf.getvalue()) is None


def test_storage_quota_and_deleting_my_files(tmp_path):
    s = settings(tmp_path, market_storage_dir=tmp_path / "market", market_storage_per_user_mb=1)
    with TestClient(create_app(s)) as c:
        signup(c, "maker_a")
        f = upload(c, "a.stl", tetra_stl(60))
        big = c.post("/market/uploads", json={"filename": "b.skp", "size": 1024 * 1024, "kind": "model"})
        assert big.status_code == 400 and big.json()["detail"]["code"] == "storage_quota_exceeded"

        # 남의 파일은 지울 수 없다
        b = signup(c, "maker_b")
        use(c, b)
        assert c.delete(f"/market/files/{f['id']}").status_code == 404
        use(c, None)
        assert c.delete(f"/market/files/{f['id']}").status_code == 401

        signup(c, "maker_c")
        g = upload(c, "g.stl", tetra_stl(40))
        item = c.post("/market/items", json=item_body(file_ids=[g["id"]])).json()
        r = c.delete(f"/market/files/{g['id']}")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "file_in_use"
        h = upload(c, "h.stl", tetra_stl(40))
        assert c.delete(f"/market/files/{h['id']}").status_code == 204
        assert c.get(f"/market/files/{h['id']}").status_code == 404
        assert [x["id"] for x in c.get("/market/files/mine").json()] == [g["id"]]
        assert item["id"]


def test_deleting_layout_share_hides_its_files_again(client):
    a = signup(client, "maker_a")
    f = upload(client, "house.stl", tetra_stl(100))
    lay = client.post("/layouts", json={
        "name": "거실 케이지", "species": "hamster", "size": "syrian",
        "cage": {"width_mm": 1000, "depth_mm": 500, "height_mm": 500},
        "items": [{"id": "a2", "asset": f"file_{f['id']}", "x_mm": 500, "y_mm": 250, "rotation_deg": 0}],
    }).json()
    first = client.post("/market/items", json=item_body(category="layout", layout_id=lay["id"])).json()
    second = client.post("/market/items", json=item_body(category="layout", layout_id=lay["id"])).json()
    assert client.delete(f"/market/files/{f['id']}").status_code == 409

    b = signup(client, "maker_b")
    use(client, b)
    assert client.get(f["mesh_url"]).status_code == 200
    use(client, a)
    assert client.delete(f"/market/items/{first['id']}").status_code == 204
    use(client, b)
    assert client.get(f["mesh_url"]).status_code == 200  # 다른 공유에 아직 들어 있다
    use(client, a)
    assert client.delete(f"/market/items/{second['id']}").status_code == 204
    use(client, b)
    assert client.get(f["mesh_url"]).status_code == 404
    use(client, a)
    assert client.get(f["mesh_url"]).status_code == 200  # 올린 사람은 계속 쓴다


def test_download_count_is_not_inflated(client):
    a = signup(client, "maker_a")
    f = upload(client, "a.stl", tetra_stl(60))
    item = client.post("/market/items", json=item_body(file_ids=[f["id"]])).json()
    url = f"/market/files/{f['id']}/download"

    def count() -> int:
        return client.get(f"/market/items/{item['id']}").json()["download_count"]

    client.get(url, follow_redirects=False)  # 올린 사람은 세지 않는다
    assert count() == 0
    use(client, None)
    for _ in range(3):
        client.get(url, follow_redirects=False)  # 같은 IP 는 1시간에 한 번
    assert count() == 1
    b = signup(client, "maker_b")
    for _ in range(3):
        client.get(url, follow_redirects=False)  # 같은 회원은 24시간에 한 번
    assert count() == 2


def test_stale_uploads_of_any_member_are_swept(client):
    from datetime import datetime, timedelta, timezone

    from app.models import MarketUpload, MarketUploadChunk

    signup(client, "maker_a")
    r = client.post("/market/uploads", json={"filename": "old.stl", "size": 200, "kind": "model"})
    old_id = r.json()["id"]
    client.put(f"/market/uploads/{old_id}/chunks/0", content=b"\0" * 200)
    with client.app.state.session_factory() as db:
        db.get(MarketUpload, old_id).created_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    signup(client, "maker_b")
    client.post("/market/uploads", json={"filename": "new.stl", "size": 200, "kind": "model"})
    with client.app.state.session_factory() as db:
        assert db.get(MarketUpload, old_id) is None
        assert db.query(MarketUploadChunk).filter_by(upload_id=old_id).count() == 0


def test_owner_can_replace_preview_image(client):
    a = signup(client, "maker_a")
    f = upload(client, "a.stl", tetra_stl(60))
    item = client.post("/market/items", json=item_body(file_ids=[f["id"]])).json()
    assert item["image"] is None
    img = upload(client, "thumb.png", PNG, kind="image")
    r = client.patch(f"/market/items/{item['id']}", json={"image_file_id": img["id"]})
    assert r.status_code == 200 and r.json()["image"]["id"] == img["id"]
    assert client.get("/market/items").json()["items"][0]["image"]["id"] == img["id"]
    # 다시 바꾸면 예전 이미지는 지워진다
    img2 = upload(client, "thumb2.png", PNG, kind="image")
    assert client.patch(f"/market/items/{item['id']}", json={"image_file_id": img2["id"]}).json()["image"]["id"] == img2["id"]
    assert client.get(f"/market/files/{img['id']}").status_code == 404
    # 모델 파일·이미 붙은 이미지는 미리보기로 쓸 수 없다
    model = upload(client, "b.stl", tetra_stl(40))
    r = client.patch(f"/market/items/{item['id']}", json={"image_file_id": model["id"]})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "wrong_file_kind"
    assert client.patch(f"/market/items/{item['id']}", json={"image_file_id": img2["id"]}).status_code == 400
    # 남의 이미지·남의 작품은 안 된다
    b = signup(client, "maker_b")
    other = upload(client, "o.png", PNG, kind="image")
    use(client, a)
    assert client.patch(f"/market/items/{item['id']}", json={"image_file_id": other["id"]}).status_code == 404
    use(client, b)
    assert client.patch(f"/market/items/{item['id']}", json={"image_file_id": other["id"]}).status_code == 403


def big_stl(target_tris: int = 120_000) -> bytes:
    """삼각형이 많은 닫힌 구 (바이너리 STL)"""
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=7, radius=40.0)  # 약 33만 삼각형
    m = trimesh.Trimesh(m.vertices, m.faces[:target_tris] if target_tris < len(m.faces) else m.faces, process=False)
    buf = io.BytesIO()
    m.export(buf, file_type="stl")
    return buf.getvalue()


def test_upload_builds_light_3d_preview_and_cleans_it_up(client):
    from app.mesh_preview import PREVIEW_MAX_TRIS, read_preview

    signup(client, "maker_a")
    data = big_stl()
    f = upload(client, "ball.stl", data)
    assert f["preview_url"] == f"/market/files/{f['id']}/preview" and 0 < f["preview_size"] < len(data) / 5
    blob = client.get(f["preview_url"]).content
    assert len(blob) == f["preview_size"]
    verts, tris = read_preview(blob)
    assert len(tris) <= PREVIEW_MAX_TRIS and tris.max() < len(verts)
    # 줄여도 외곽 크기는 그대로 (좌표 한 칸 정도 오차)
    assert all(abs(a - b) < 0.5 for a, b in zip(verts.max(0) - verts.min(0), f["dims_mm"]))

    # 작은 파일·SKP 도 미리보기가 있거나(그대로 묶음) 없다
    small = upload(client, "tetra.stl", tetra_stl(50))
    assert read_preview(client.get(small["preview_url"]).content)[1].shape == (4, 3)
    skp = upload(client, "a.skp", skp_bytes(2048))
    assert skp["preview_url"] is None and skp["preview_size"] is None

    # 파일을 지우면 미리보기도 저장소에서 지운다
    root = client.app.state.market_storage.root
    assert (root / f"market/{f['id']}/{f['id']}.preview.nfm").exists()
    assert client.delete(f"/market/files/{f['id']}").status_code == 204
    assert not (root / f"market/{f['id']}").exists() or not any((root / f"market/{f['id']}").iterdir())


def test_preview_failure_does_not_block_upload(client, monkeypatch):
    import app.api.market as market_api

    monkeypatch.setattr(market_api, "build_preview", lambda fmt, data: None)
    signup(client, "maker_a")
    f = upload(client, "a.stl", tetra_stl(60))
    assert f["preview_url"] is None and f["mesh_url"]


def test_admin_backfills_missing_previews(client, monkeypatch):
    import app.api.market as market_api
    from app.models import MarketFile

    signup(client, "maker_a")
    real = market_api.build_preview
    monkeypatch.setattr(market_api, "build_preview", lambda fmt, data: None)
    f = upload(client, "old.stl", tetra_stl(60))
    with client.app.state.session_factory() as db:  # 예전 파일처럼 표시 없음으로
        db.get(MarketFile, f["id"]).preview_size = None
        db.commit()
    monkeypatch.setattr(market_api, "build_preview", real)
    assert client.post("/market/files/previews/backfill").status_code == 403
    admin_login(client)
    r = client.post("/market/files/previews/backfill")
    assert r.status_code == 200 and r.json() == {"done": 1, "failed": 0, "remaining": 0}
    with client.app.state.session_factory() as db:  # 올린 사람만 볼 수 있는 파일이라 DB 로 확인
        assert db.get(MarketFile, f["id"]).preview_size > 0
    assert client.post("/market/files/previews/backfill").json()["done"] == 0
