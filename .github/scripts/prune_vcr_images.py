#!/usr/bin/env python3
"""Vercel 컨테이너 저장소(VCR)의 오래된 이미지를 지운다.

배포마다 백엔드 이미지가 하나씩 쌓이고, 저장소가 가득 차면(50개) 다음 배포의
이미지 푸시가 거부된다. Vercel에는 자동 보존 정책이 없어서 이 스크립트로 정리한다.

남기는 것:
  - 최근 KEEP개 (생성 시각 기준)
  - 지금 프로덕션 배포가 쓰는 이미지 (커밋 SHA 앞 12자리 태그)
나머지는 지운다. 프로덕션 이미지를 찾지 못하면 아무것도 지우지 않고 실패한다.

환경변수:
  VERCEL_TOKEN       필수. 팀 범위 토큰
  VERCEL_TEAM_ID     필수
  VERCEL_PROJECT_ID  필수
  VCR_REPOSITORY     기본 backend
  KEEP               기본 10
  DRY_RUN            true면 지우지 않고 목록만 출력
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.vercel.com"


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, "").strip() or default
    if value is None:
        sys.exit(f"환경변수 {name} 이(가) 없습니다.")
    return value


TOKEN = env("VERCEL_TOKEN")
TEAM_ID = env("VERCEL_TEAM_ID")
PROJECT_ID = env("VERCEL_PROJECT_ID")
REPOSITORY = env("VCR_REPOSITORY", "backend")
DRY_RUN = env("DRY_RUN", "false").lower() in ("1", "true", "yes")


def api(method: str, path: str, **params: str) -> dict:
    query = urllib.parse.urlencode({"teamId": TEAM_ID, **params})
    request = urllib.request.Request(
        f"{API}{path}?{query}",
        method=method,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"{method} {path} -> HTTP {error.code}: {detail}") from None
    return json.loads(body) if body.strip() else {}


def list_images() -> list[dict]:
    images: list[dict] = []
    cursor = None
    while True:
        params = {"projectId": PROJECT_ID, "limit": "100"}
        if cursor:
            params["cursor"] = cursor
        page = api("GET", f"/v1/vcr/repository/{REPOSITORY}/images", **params)
        images.extend(page.get("images", []))
        cursor = page.get("nextCursor")
        if not cursor:
            return images


def production_sha() -> str:
    project = api("GET", f"/v9/projects/{PROJECT_ID}")
    production = (project.get("targets") or {}).get("production") or {}
    sha = (production.get("meta") or {}).get("githubCommitSha") or ""
    if not sha:
        sys.exit("프로덕션 배포의 커밋 SHA를 찾지 못했습니다. 아무것도 지우지 않습니다.")
    print(f"프로덕션 배포: {production.get('id')} (커밋 {sha[:12]})")
    return sha


def describe(image: dict) -> str:
    tags = ",".join(image.get("tags") or []) or "(태그 없음)"
    return f"{image['id']}  {image['createdAt']}  {tags}"


def main() -> int:
    try:
        keep_count = int(env("KEEP", "10"))
    except ValueError:
        sys.exit("KEEP은 정수여야 합니다.")
    if keep_count < 1:
        sys.exit("KEEP은 1 이상이어야 합니다.")

    sha = production_sha()
    images = sorted(list_images(), key=lambda image: image["createdAt"], reverse=True)

    # 이미지 태그는 커밋 SHA 앞 12자리다.
    protected = {
        image["id"]
        for image in images
        if any(len(tag) >= 7 and sha.startswith(tag) for tag in image.get("tags") or [])
    }
    if not protected:
        sys.exit(
            f"프로덕션 이미지(태그 {sha[:12]})를 저장소에서 찾지 못했습니다. "
            "아무것도 지우지 않습니다."
        )

    keep = [
        image
        for index, image in enumerate(images)
        if index < keep_count or image["id"] in protected
    ]
    keep_ids = {image["id"] for image in keep}
    delete = [image for image in images if image["id"] not in keep_ids]

    print(f"전체 {len(images)}개 / 남길 것 {len(keep)}개 / 지울 것 {len(delete)}개")
    for image in keep:
        mark = "프로덕션" if image["id"] in protected else "최근"
        print(f"  남김({mark})  {describe(image)}")
    for image in delete:
        print(f"  지움        {describe(image)}")

    if DRY_RUN:
        print("DRY_RUN: 지우지 않았습니다.")
        return 0

    failed = 0
    for image in delete:
        try:
            api(
                "DELETE",
                f"/v1/vcr/repository/{REPOSITORY}/images/{image['id']}",
                projectId=PROJECT_ID,
            )
        except RuntimeError as error:
            failed += 1
            print(f"삭제 실패: {error}", file=sys.stderr)
    print(f"삭제 {len(delete) - failed}개 완료, 실패 {failed}개")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        sys.exit(str(error))
