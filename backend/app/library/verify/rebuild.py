"""새 프로세스에서 다시 만들기 (G12 결정성). `python -I` 로 띄워 사용자 site·환경 변수·현재 디렉터리의 영향을 없앤다.

입력 (표준 입력 JSON): {"key": 템플릿 key, "params": 파라미터, "draft": 초안 부품 파일 dict 또는 null}
출력 (표준 출력 JSON): {"files": {파일 이름: sha256}}  — geometry.file_digests 와 같은 파일들

`python -I` 는 sys.path 에 현재 디렉터리를 넣지 않고 PYTHONPATH 도 읽지 않는다. 백엔드는 설치하는 패키지가 아니라서
(pyproject: package = false) `-I -m app.library.verify.rebuild` 로는 app 을 찾지 못한다. 그래서 `-I -c` 로 백엔드
디렉터리 하나만 sys.path 앞에 넣고 main() 을 부른다 (격리는 그대로).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[3]
TIMEOUT_S = 120


def clear_build_cache(t: Any) -> None:
    """DSL 부품의 형상 기억을 비운다 (같은 프로세스 두 번째 빌드가 기억이 아닌 새 빌드가 되게). 코드 부품은 없음."""
    cache = getattr(t, "_cache", None)
    lock = getattr(t, "_lock", None)
    if cache is None:
        return
    if lock is not None:
        with lock:
            cache.clear()
    else:
        cache.clear()


def digests_for(key: str, params: dict, draft: dict | None) -> dict[str, str]:
    from app.config import BACKEND_DIR as APP_DIR
    from app.domain import PlacementHint
    from app.library.verify.geometry import file_digests
    from app.rules.loader import load_rules
    from app.services.engine import build_item

    if draft is not None:
        from app.library.template import make_template

        t = make_template(draft, key=key)
    else:
        from app.templates.registry import get_template

        t = get_template(key)
    p = t.Params.model_validate(params)
    rules = load_rules(APP_DIR / "rules")
    return file_digests(build_item(0, t, p, PlacementHint(), rules.printing))


def fresh_process_digests(key: str, params: dict, draft: dict | None = None) -> dict[str, str]:
    code = (f"import sys; sys.path.insert(0, {str(BACKEND_DIR)!r}); "
            "from app.library.verify.rebuild import main; main()")
    proc = subprocess.run([sys.executable, "-I", "-c", code], input=json.dumps(
        {"key": key, "params": params, "draft": draft}), capture_output=True, text=True, timeout=TIMEOUT_S,
        cwd=str(BACKEND_DIR), check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"rebuild process failed ({proc.returncode}): {proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])["files"]


def main() -> None:
    req = json.loads(sys.stdin.read())
    files = digests_for(req["key"], req["params"], req.get("draft"))
    sys.stdout.write(json.dumps({"files": files}, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
