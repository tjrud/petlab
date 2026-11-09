"""설계 생성·수정·내보내기 서비스.

파이프라인: 사육 환경 + 프롬프트 → LLM 해석(DesignSpec) → 엔진(보정·형상·배치·검증) → 버전 저장.
수정 시 직전 버전의 '보정 반영 명세'를 LLM 에 맥락으로 주고 새 버전을 만든다 (이전 버전 유지).
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import threading
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.errors import InvalidInputError, NotFoundError
from app.geometry.fingerprint import file_digest
from app.i18n import get_lang
from app.llm.base import HabitatInfo, Interpreter, InterpretRequest, InterpretResult
from app.models import (
    Design,
    DesignVersion,
    Habitat,
    MarketEvent,
    MarketItem,
    Pet,
    Post,
    User,
    WaitlistEntry,
)
from app.rules.loader import RuleBook
from app.schemas import (
    ID_RE,
    CageIn,
    DesignListItem,
    DesignListOut,
    DesignOut,
    HabitatIn,
    HabitatKind,
    HabitatOut,
    ItemOut,
    PlacementOut,
    SharedDesignOut,
    VersionOut,
    VersionSummary,
)
from app.services import usage
from app.services.market_view import item_models, stored_blobs
from app.storage import Stored

if TYPE_CHECKING:  # 형상 커널(build123d/OCP)·trimesh 는 설계 생성·메시·내려받기 요청에서만 불러온다
    from app.domain import BuiltItem, Cage
    from app.geometry.export import ExportFile
    from app.services.engine import EngineContext, EngineResult


# ── 무거운 모듈을 처음 쓸 때 불러오는 얇은 함수 (테스트가 모듈 속성으로 바꿔 끼울 수 있게 이름을 유지) ──
def run_engine(*a, **k):
    from app.services.engine import run_engine as f
    return f(*a, **k)


def build_item(*a, **k):
    from app.services.engine import build_item as f
    return f(*a, **k)


def revalidate(*a, **k):
    from app.services.engine import revalidate as f
    return f(*a, **k)


def get_template(*a, **k):
    from app.templates.registry import get_template as f
    return f(*a, **k)


def rule_change_notices(*a, **k):
    from app.validation.autofix import rule_change_notices as f
    return f(*a, **k)


def parse_spec(*a, **k):
    from app.llm.spec import parse_spec as f
    return f(*a, **k)


def to_item_specs(*a, **k):
    from app.llm.spec import to_item_specs as f
    return f(*a, **k)


def geometry_fingerprint(*a, **k):
    from app.geometry.fingerprint import geometry_fingerprint as f
    return f(*a, **k)


def export_parts(*a, **k):
    from app.geometry.export import export_parts as f
    return f(*a, **k)

log = logging.getLogger(__name__)


class ExportBlockedError(RuntimeError):
    def __init__(self, message_ko: str, errors: list[dict]):
        super().__init__(message_ko)
        self.message_ko = message_ko
        self.errors = errors


class MeshRegenerationError(RuntimeError):
    """저장된 파라미터로 메시를 다시 만들 수 없을 때 (템플릿 변경 등)."""

    def __init__(self, message_ko: str):
        super().__init__(message_ko)
        self.message_ko = message_ko


class GeometryChangedError(MeshRegenerationError):
    """다시 만든 형상이 저장할 때 검증한 형상과 같다고 확인되지 않았고, 다시 검증해도 통과하지 못할 때."""

    MESSAGE_KO = (
        "이 설계 버전을 만든 뒤 서비스가 업데이트되어, 지금 다시 만든 형상이 처음 검증한 형상과 같다고 확인할 수 "
        "없었어요. 다시 검증해 보니 안전 기준을 통과하지 못해 내려받을 수 없어요. 같은 요청으로 새 버전을 만들어 주세요."
    )

    def __init__(self, errors: list[dict]):
        super().__init__(self.MESSAGE_KO)
        self.errors = errors


def _atomic_write(path: Path, data: bytes) -> None:
    """임시 파일에 쓴 뒤 os.replace 로 바꿔 끼운다. 동시에 읽는 요청이 반쯤 쓰인 파일을 받지 않게 한다."""
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _print_name(index: int) -> str:
    """출력 자세 메시 캐시 파일 이름 (내려받기용)."""
    return f"print_{index}.stl"


def _world_name(index: int) -> str:
    """케이지 좌표계 뷰어 메시 캐시 파일 이름 (배치된 구조물만)."""
    return f"world_{index}.stl"


def _cache_names(it: dict) -> list[str]:
    """저장된 구조물 하나(DesignVersion.items 의 항목)가 캐시에 가져야 할 파일 이름."""
    names = [_print_name(it["index"])]
    if it["placement"]:
        names.append(_world_name(it["index"]))
    return names


def _mesh_files(item: BuiltItem) -> dict[str, bytes]:
    """구조물 하나의 메시 캐시 파일: 출력 자세(print_i), 배치된 경우 케이지 좌표계 뷰어 메시(world_i)."""
    files = {_print_name(item.index): item.print_mesh.export(file_type="stl")}
    if item.placement is not None:
        files[_world_name(item.index)] = item.world_mesh().export(file_type="stl")
    return files


def _cache_files(items: Iterable[BuiltItem]) -> dict[str, bytes]:
    """여러 구조물의 메시 캐시 파일을 구조물 순서대로 합친다."""
    files: dict[str, bytes] = {}
    for item in items:
        files.update(_mesh_files(item))
    return files


def _write_cache(d: Path, files: dict[str, bytes]) -> None:
    """버전 캐시 디렉터리에 파일을 하나씩 원자적으로 쓴다."""
    d.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        _atomic_write(d / name, data)


def _version_records(llm_spec: dict, engine: EngineResult) -> tuple[list[dict], dict]:
    """엔진 결과를 저장할 기록으로 바꾼다: (DesignVersion.items, 보정 반영 명세 effective_spec).

    llm_spec 은 바꾸지 않는다. 만들어진 구조물만 effective_spec 의 items 가 되고, 하나도 만들어지지 않았으면
    effective_spec 은 llm_spec 과 같다. 저장되는 JSON 의 키 순서가 바뀌지 않도록 항목 dict 를 이 순서로 만든다."""
    effective = copy.deepcopy(llm_spec)
    built_items = []
    effective_items = []
    for it in engine.items:
        src = llm_spec["items"][it.index]
        params = it.params.model_dump(mode="json") if it.params is not None else src["params"]
        effective_items.append({**copy.deepcopy(src), "params": params})
        lo, hi = it.mesh.bounds
        built_items.append({
            "index": it.index,
            "template": it.key,
            "label_ko": it.label_ko,
            "params": params,
            "reason_ko": src.get("reason_ko", ""),
            "hint": src["placement"],
            "placement": (
                {"x_mm": it.placement.x_mm, "y_mm": it.placement.y_mm, "rotation_deg": it.placement.rotation_deg}
                if it.placement else None
            ),
            "size_mm": [float(v) for v in (hi - lo)],
            "print_size_mm": [float(v) for v in it.print_mesh.extents],
        })
    if effective_items:
        effective["items"] = effective_items
    return built_items, effective


@dataclass(frozen=True)
class _Generated:
    """LLM 해석과 엔진 실행 결과 (아직 저장하지 않음)."""

    prompt: str
    interpret: InterpretResult
    engine: EngineResult


@dataclass(frozen=True)
class DesignLimits:
    """최근 24시간 설계 요청(LLM 호출) 횟수 상한. 관리자는 적용하지 않는다.
    per_user·global_ 은 0 이면 막음, per_ip 는 0 이면 IP 별 제한 없음."""

    per_user: int = 20
    global_: int = 300
    per_ip: int = 40


TITLE_LEN = 40


def make_title(prompt: str) -> str:
    """설계 제목: 사용자가 쓴 첫 요청의 첫 줄 (길면 줄임표). LLM 설명문보다 짧고 본인이 알아보기 쉽다."""
    first = next((line.strip() for line in prompt.splitlines() if line.strip()), "") or "맞춤 설계"
    return first if len(first) <= TITLE_LEN else first[: TITLE_LEN - 1].rstrip() + "…"


def _can_edit(design: Design, user: User) -> bool:
    """수정·공유 권한: 소유자만. 소유자가 없는 옛 설계(회원 기능 이전)는 관리자가 소유자다.
    관리자도 회원의 설계를 대신 공유·수정하지는 못한다 (볼 수만 있다: _can_view_all)."""
    if design.owner_id is None:
        return user.is_admin
    return design.owner_id == user.id


def _can_view_all(design: Design, user: User | None) -> bool:
    """모든 버전을 볼 수 있는지: 소유자, 또는 관리자(운영·신고 처리)."""
    return user is not None and (user.is_admin or _can_edit(design, user))


def _unresolved_errors(issues: list[dict]) -> list[dict]:
    """자동 보정되지 않은 오류만 고른다.

    저장된 보고서용. ValidationReport.errors 와 같은 기준이고, 옛 보고서를 pydantic 으로 다시 읽지 않는다."""
    return [i for i in issues if i["severity"] == "error" and not i.get("auto_fixed")]


def _exportable(v: DesignVersion) -> bool:
    """내려받을 수 있는 버전인지: 검증을 통과했고 구조물이 하나 이상 있다."""
    return v.passed and bool(v.items)


class DesignService:
    def __init__(self, rules: RuleBook, interpreter: Callable[[], Interpreter], mesh_dir: Path,
                 limits: DesignLimits | None = None):
        self.rules = rules
        self._interpreter = interpreter
        self.mesh_dir = Path(mesh_dir)
        self.limits = limits or DesignLimits()
        self._locks_guard = threading.Lock()
        self._version_locks: dict[str, threading.Lock] = {}
        # 다시 검증에 실패한 버전 → 오류 목록. 같은 코드로 실행되는 동안 결과는 바뀌지 않으므로, 요청마다
        # 형상 생성·검증을 되풀이하지 않고 바로 막는다 (공유된 설계의 뷰어가 메시를 여러 번 요청해도 가볍게).
        self._geometry_blocked: dict[tuple[str, int], list[dict]] = {}

    def _version_lock(self, design_id: str, version: int) -> threading.Lock:
        """버전별 메시 재생성 잠금 (같은 버전을 동시에 여러 번 만들지 않도록)."""
        key = f"{design_id}/{version}"
        with self._locks_guard:
            return self._version_locks.setdefault(key, threading.Lock())

    # ── 사육 환경 ───────────────────────────────────────────

    def check_habitat(self, species: str, size: str, count: int | None = None) -> None:
        """규칙 파일에 있는 종·크기인지, count 를 주면 종별 최대 마릿수(max_count) 이하인지 확인한다.
        사육 환경 등록(count 와 함께)·반려동물·배치안 저장(종·크기만)이 쓴다."""
        try:
            self.rules.size_rules(species, size)
        except KeyError:
            raise InvalidInputError(f"지원하지 않는 종/크기입니다: {species}/{size}") from None
        if count is not None:
            entry = self.rules.species_entry(species)
            if count > entry.max_count:
                raise InvalidInputError(f"{entry.display_name}은(는) 최대 {entry.max_count}마리까지 입력할 수 있습니다.")

    def habitat_kind(self, species: str) -> HabitatKind:
        """사육 환경 종류 (cage / aquarium). 규칙 파일에서 빠진 종(옛 행)은 cage 로 본다 (500 이 나지 않게)."""
        try:
            return self.rules.habitat(species)
        except KeyError:
            return "cage"

    def check_virtual_cage(self, species: str) -> None:
        """가상 케이지(배치안)는 케이지 종만 지원한다 (에셋·배치 검토가 케이지 기준). 규칙에서 빠진 종은 막지 않는다
        (check_habitat 이 먼저 걸러내고, 탐색에서 담아 오는 옛 배치는 예전처럼 담긴다)."""
        if self.habitat_kind(species) != "cage":
            raise InvalidInputError("가상 케이지는 케이지에서 키우는 동물만 지원합니다.", code="virtual_cage_unsupported")

    def create_habitat(self, db: Session, data: HabitatIn, user: User) -> Habitat:
        self.check_habitat(data.species, data.size, data.count)
        if data.pet_id is not None:
            pet = db.get(Pet, data.pet_id)
            if pet is None or pet.owner_id != user.id:
                raise NotFoundError("반려동물 정보를 찾을 수 없습니다.")
            if pet.species != data.species:
                # 반려동물(예: 햄스터) 정보로 다른 종(예: 어항)의 사육 환경을 만들지 않는다
                raise InvalidInputError("반려동물 정보와 종이 다릅니다.", code="pet_species_mismatch")
        h = Habitat(
            owner_id=user.id, pet_id=data.pet_id,
            species=data.species, size=data.size, count=data.count,
            cage_width_mm=data.cage.width_mm, cage_depth_mm=data.cage.depth_mm, cage_height_mm=data.cage.height_mm,
        )
        db.add(h)
        db.commit()
        return h

    def get_habitat(self, db: Session, habitat_id: str, user: User) -> Habitat:
        h = db.get(Habitat, habitat_id) if ID_RE.fullmatch(habitat_id) else None
        # 남의 사육 환경은 없는 것과 같이 다룬다 (존재 여부도 알리지 않음)
        if h is None or not (user.is_admin or (h.owner_id is not None and h.owner_id == user.id)):
            raise NotFoundError("사육 환경을 찾을 수 없습니다.")
        return h

    def habitat_out(self, h: Habitat, owner_view: bool = True) -> HabitatOut:
        """owner_view 가 아니면(공유된 설계를 다른 사람이 볼 때) 반려동물 ID 는 빼고 보낸다."""
        species_name, size_name = self.rules.display_names(h.species, h.size)
        return HabitatOut(
            id=h.id, pet_id=h.pet_id if owner_view else None, species=h.species, species_name_ko=species_name,
            size=h.size, size_name_ko=size_name, habitat_kind=self.habitat_kind(h.species), count=h.count,
            cage=CageIn(width_mm=h.cage_width_mm, depth_mm=h.cage_depth_mm, height_mm=h.cage_height_mm),
            created_at=h.created_at,
        )

    def shared_design_out(self, d: Design, v: DesignVersion) -> SharedDesignOut:
        """커뮤니티 글·탐색 작품에 붙은 설계 버전 요약 (누구나 보는 화면)."""
        return SharedDesignOut(
            id=d.id, version=v.version, title=self.title_of(d), summary_ko=v.llm_spec.get("summary_ko", ""),
            item_labels=[it["label_ko"] for it in v.items], passed=v.passed,
            habitat=self.habitat_out(d.habitat, owner_view=False),
        )

    @staticmethod
    def _cage(h: Habitat) -> Cage:
        from app.domain import Cage
        return Cage(h.cage_width_mm, h.cage_depth_mm, h.cage_height_mm)

    def _engine_ctx(self, h: Habitat) -> EngineContext:
        from app.services.engine import EngineContext
        return EngineContext(cage=self._cage(h), species=h.species, size=h.size, count=h.count, rules=self.rules)

    # ── 설계 생성 / 수정 ─────────────────────────────────────

    def quota(self, db: Session, user: User) -> dict[str, int | None]:
        """최근 24시간 설계 요청 횟수와 상한 (관리자는 상한 없음 → None). 실패한 요청도 센다."""
        used = usage.count(db, "design", user_id=user.id)
        limit = None if user.is_admin else self.limits.per_user
        return {"used": used, "limit": limit, "remaining": None if limit is None else max(0, limit - used)}

    def reserve_quota(self, db: Session, user: User, ip_key: str | None) -> None:
        """LLM 을 부르기 전에 사용량 1회를 기록한다 (상한에 닿았으면 429). 동시 요청도 상한을 넘지 못한다."""
        if user.is_admin:
            db.commit()  # 상한은 없지만 LLM 호출 동안 읽기 트랜잭션을 열어 두지 않는다
            return
        lim = self.limits
        usage.reserve(
            db, "design", user, ip_key=ip_key,
            per_user=usage.Cap(lim.per_user, f"최근 24시간 동안 쓸 수 있는 설계 횟수({lim.per_user}회)를 모두 썼어요. "
                                             "잠시 뒤 다시 시도해 주세요.", "design_quota_exceeded"),
            per_ip=usage.Cap(lim.per_ip, "이 네트워크에서 최근 24시간 동안 설계 요청이 너무 많았어요. 잠시 뒤 다시 시도해 주세요.",
                             "design_quota_exceeded") if lim.per_ip > 0 else None,
            global_=usage.Cap(lim.global_, "오늘은 서비스 전체 설계 요청이 많아 잠시 쉬어 가요. 나중에 다시 시도해 주세요.",
                              "design_capacity_exceeded"),
        )

    def create_design(self, db: Session, habitat_id: str, prompt: str, user: User,
                      ip_key: str | None = None) -> tuple[Design, DesignVersion]:
        h = self.get_habitat(db, habitat_id, user)
        # 규칙 파일에서 빠진 종·크기의 옛 사육 환경은 사용량을 쓰기 전에 막는다 (예전에는 해석 단계에서 500)
        self.check_habitat(h.species, h.size)
        # 사용량을 먼저 기록하고 커밋한다 (LLM 호출 수십 초 동안 DB 연결을 '트랜잭션 중' 상태로 잡아 두지 않는다)
        self.reserve_quota(db, user, ip_key)
        generated = self._generate(h, prompt, previous=None)  # LLM 실패 시 예외 → 아무것도 저장하지 않음
        design = Design(habitat_id=h.id, owner_id=user.id, title=make_title(prompt))
        db.add(design)
        db.flush()
        row = self._save_version(db, design, generated, 1, user)
        db.commit()
        return design, row

    def revise_design(
        self, db: Session, design_id: str, prompt: str, user: User, base_version: int | None = None,
        ip_key: str | None = None,
    ) -> tuple[Design, DesignVersion]:
        design = self.get_editable_design(db, design_id, user)
        base = self.get_version(db, design, base_version)
        previous = self._previous_spec(base)
        habitat = design.habitat
        self.check_habitat(habitat.species, habitat.size)  # create_design 과 같은 까닭
        self.reserve_quota(db, user, ip_key)  # 기록 후 커밋 (create_design 과 같은 이유)
        generated = self._generate(habitat, prompt, previous=previous)
        # 해석하는 동안(최대 1분) 다른 창에서 설계를 지웠으면 새 버전을 붙이지 않는다.
        # 행 잠금(Postgres)으로 저장이 끝날 때까지 삭제가 끼어들지 못하게 한다 (SQLite 는 저장 직후 다시 확인한다)
        if db.scalar(select(Design.id).where(Design.id == design.id).with_for_update()) is None:
            raise NotFoundError("설계가 삭제되었어요.")
        next_no = (db.scalar(select(func.max(DesignVersion.version)).where(DesignVersion.design_id == design.id)) or 0) + 1
        row = self._save_version(db, design, generated, next_no, user)
        db.commit()
        db.refresh(design)
        return design, row

    @staticmethod
    def _with_legacy_defaults(spec: dict) -> dict:
        """저장 당시 없던 파라미터를 legacy_defaults 로 채운다 (메시 재생성과 같은 형상을 LLM 에게 보여 주도록)."""
        items = []
        for it in spec.get("items") or []:
            if not isinstance(it, dict):  # 형식 오류는 parse_spec 이 걸러낸다
                items.append(it)
                continue
            try:
                legacy = get_template(it.get("template")).legacy_defaults
            except Exception:  # 알 수 없는 템플릿도 parse_spec 이 걸러낸다
                legacy = {}
            if legacy and isinstance(it.get("params"), dict):
                it = {**it, "params": {**legacy, **it["params"]}}
            items.append(it)
        return {**spec, "items": items}

    @classmethod
    def _previous_spec(cls, base: DesignVersion) -> BaseModel | None:
        for candidate in (base.effective_spec, base.llm_spec):
            try:
                return parse_spec(json.dumps(cls._with_legacy_defaults(candidate), ensure_ascii=False))
            except Exception:  # 검증 실패 시 다음 후보
                continue
        return None

    def _generate(self, h: Habitat, prompt: str, previous: BaseModel | None) -> _Generated:
        # 엔진 맥락을 한 번 만들어 LLM 요청과 엔진 실행에 함께 쓴다. 규칙 조회(KeyError)는 예전과 같은 순서로 일어난다:
        # 크기 규칙 → 종 이름 → 최소 벽 두께
        ctx = self._engine_ctx(h)
        size_rules = ctx.size_rules
        entry = self.rules.species_entry(h.species)
        req = InterpretRequest(
            prompt=prompt,
            # 어항이면 cage 는 수조 안쪽 가로·세로와 물 깊이(바닥재 위~수면)
            habitat=HabitatInfo(h.species, entry.display_name, h.size, h.count, ctx.cage, habitat=entry.habitat),
            size_rules=size_rules,
            min_wall_mm=ctx.min_wall_mm,
            previous=previous,
            language=get_lang(),  # 영어 페이지에서 만들면 설명(summary_ko 등)도 영어로
            allowed_templates=entry.allowed_templates,  # 이 종에 만들 수 있는 구조물만 LLM 에게 보인다
        )
        result = self._interpreter().interpret(req)
        engine_result = run_engine(to_item_specs(result.spec), ctx)
        return _Generated(prompt=prompt, interpret=result, engine=engine_result)

    def _save_version(self, db: Session, design: Design, g: _Generated, version_no: int, user: User) -> DesignVersion:
        """생성 결과를 새 버전 행으로 저장하고 메시 캐시를 쓴다. g 는 바꾸지 않는다.
        flush 가 실패하면(버전 번호 경쟁 등) 캐시 파일을 쓰지 않도록 파일은 마지막에 쓴다."""
        llm_spec = g.interpret.spec.model_dump(mode="json")
        engine = g.engine
        built_items, effective = _version_records(llm_spec, engine)

        # 검증한 형상 그대로의 메시 파일. 해시를 함께 저장해 두고, 캐시를 다시 만들 때 같은 형상인지 확인한다
        files = _cache_files(engine.items)
        geometry = {
            "fingerprint": geometry_fingerprint((it.key for it in engine.items), self.rules.printing),
            "files": {name: file_digest(data) for name, data in files.items()},
        }
        row = DesignVersion(
            design_id=design.id, version=version_no, prompt=g.prompt,
            provider=g.interpret.provider, llm_attempts=g.interpret.attempts,
            llm_spec=llm_spec, effective_spec=effective, items=built_items,
            report=engine.report.model_dump(mode="json"), passed=engine.report.passed, geometry=geometry,
            created_by=user.id,
        )
        db.add(row)
        db.flush()
        # 쓰기를 시작한 뒤(SQLite 는 이때부터 다른 쓰기를 막는다) 설계가 아직 있는지 확인한다: 그사이 지워졌으면
        # 버전을 붙이지 않는다 (요청이 끝나면 세션이 되돌린다). 캐시도 쓰지 않는다
        if db.scalar(select(Design.id).where(Design.id == design.id)) is None:
            raise NotFoundError("설계가 삭제되었어요.")
        # 메시 캐시 저장 (뷰어용 배치 메시 + 출력 자세 메시)
        _write_cache(self._version_dir(design.id, version_no), files)
        return row

    # ── 조회 ────────────────────────────────────────────────

    def get_design(self, db: Session, design_id: str) -> Design:
        """권한 확인 없이 찾는다. API 에서는 get_visible / get_editable_design 을 쓴다."""
        d = db.get(Design, design_id) if ID_RE.fullmatch(design_id) else None
        if d is None:
            raise NotFoundError("설계를 찾을 수 없습니다.")
        return d

    @staticmethod
    def shared_versions(db: Session, design_id: str) -> list[int]:
        """커뮤니티 글에 첨부된 버전 (누구나 볼 수 있다)."""
        rows = db.scalars(select(Post.design_version).where(Post.design_id == design_id,
                                                            Post.design_version.is_not(None)).distinct())
        return sorted(set(rows))

    def get_visible(self, db: Session, design_id: str, user: User | None) -> tuple[Design, set[int] | None]:
        """볼 수 있는 설계와 볼 수 있는 버전 (None = 모든 버전).

        소유자·관리자는 모든 버전, 그 밖의 사람은 커뮤니티 글에 첨부된 버전만 본다
        (공유한 뒤에 만든 버전이나 공유하지 않은 이전 버전은 보이지 않는다). 볼 수 있는 버전이 없으면 404."""
        d = self.get_design(db, design_id)
        if _can_view_all(d, user):
            return d, None
        allowed = set(self.shared_versions(db, d.id))
        if not allowed:
            raise NotFoundError("설계를 찾을 수 없습니다.")
        return d, allowed

    def get_editable_design(self, db: Session, design_id: str, user: User) -> Design:
        d = self.get_design(db, design_id)
        if not _can_edit(d, user):
            raise NotFoundError("설계를 찾을 수 없습니다.")
        return d

    def delete_design(self, db: Session, design_id: str, user: User) -> list[Stored]:
        """설계와 모든 버전을 지운다 (소유자만: 관리자도 회원의 설계는 지우지 못한다, _can_edit).
        저장소(Blob)에서 지워야 할 파일을 돌려준다 (커밋한 뒤 호출하는 쪽이 지운다).

        커뮤니티 글·탐색 작품·제작 신청에 첨부되어 있으면 연결만 끊는다 (글·작품은 남는다). 다만 이 설계만 담은
        탐색 작품(3D 파일·배치 예시 없이 대표 이미지만 있을 수 있음)은 빈 작품이 되므로 함께 지운다
        (소개 글은 작품을 지울 때처럼 남긴다).
        사육 환경 행은 다른 설계나 설계 화면이 다시 쓸 수 있어 남긴다. 사용량 기록도 남는다
        (지우고 다시 만들어 하루 상한을 피하지 못하게)."""
        d = self.get_editable_design(db, design_id, user)
        did = d.id
        # 같은 설계에 대한 수정 요청과 차례를 정한다 (Postgres 행 잠금. revise_design 도 저장 전에 같은 잠금을 잡는다)
        db.execute(select(Design.id).where(Design.id == did).with_for_update())
        db.execute(update(Post).where(Post.design_id == did).values(design_id=None, design_version=None))
        stored: list[Stored] = []
        for item in db.scalars(select(MarketItem).where(MarketItem.design_id == did)):
            if item_models(item) or item.layout:
                item.design_id = item.design_version = None
                continue
            for f in list(item.files):  # 대표 이미지
                stored += stored_blobs(f)
                db.delete(f)
            db.execute(delete(MarketEvent).where(MarketEvent.item_id == item.id))
            db.delete(item)
        db.execute(update(WaitlistEntry).where(WaitlistEntry.design_id == did).values(design_id=None, version=None))
        db.flush()  # 위의 작품 변경을 설계 행을 지우기 전에 DB 에 반영한다 (아래 delete 문은 자동으로 flush 하지 않는다)
        # 버전은 잠금을 잡은 뒤에 지운다 (잠금을 기다리는 사이 커밋된 새 버전까지)
        db.execute(delete(DesignVersion).where(DesignVersion.design_id == did))
        db.expunge(d)
        db.execute(delete(Design).where(Design.id == did))
        db.commit()
        # 메시 캐시는 DB 에서 지운 뒤에 지운다 (캐시는 다시 만들 수 있어 지우다 실패해도 DB 와 어긋나지 않는다)
        shutil.rmtree(self.mesh_dir / did, ignore_errors=True)
        return stored

    def list_designs(self, db: Session, user: User, page: int, page_size: int) -> DesignListOut:
        """내 설계 목록 (최근 수정순). 관리자는 소유자가 없는 옛 설계도 함께 본다."""
        cond = Design.owner_id == user.id
        if user.is_admin:
            cond = cond | Design.owner_id.is_(None)
        latest = (select(DesignVersion.design_id, func.max(DesignVersion.created_at).label("updated"),
                         func.count(DesignVersion.id).label("n"), func.max(DesignVersion.version).label("last"))
                  .group_by(DesignVersion.design_id).subquery())
        total = db.scalar(select(func.count(Design.id)).where(cond)) or 0
        rows = db.execute(
            select(Design, latest.c.updated, latest.c.n, latest.c.last)
            .options(selectinload(Design.habitat))
            .join(latest, latest.c.design_id == Design.id)
            .where(cond)
            .order_by(latest.c.updated.desc(), Design.id)
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        ids = [r[0].id for r in rows]
        shared_ids, passed, pets = set(), {}, {}
        if rows:
            shared_ids = set(db.scalars(select(Post.design_id).where(Post.design_id.in_(ids))))
            # 각 설계의 최신 버전 검증 결과만 읽는다 (버전 JSON 전체를 불러오지 않게)
            passed = dict(db.execute(
                select(DesignVersion.design_id, DesignVersion.passed)
                .join(latest, (latest.c.design_id == DesignVersion.design_id) & (latest.c.last == DesignVersion.version))
                .where(DesignVersion.design_id.in_(ids))
            ).all())
            pet_ids = {d.habitat.pet_id for d, *_ in rows if d.habitat.pet_id}
            if pet_ids:
                pets = {p.id: p.name for p in db.scalars(select(Pet).where(Pet.id.in_(pet_ids)))}
        items = []
        for d, updated, n, last in rows:
            items.append(DesignListItem(
                id=d.id, title=d.title or self.title_of(d), created_at=d.created_at, updated_at=updated,
                version_count=n, latest_version=last, latest_passed=bool(passed.get(d.id)),
                habitat=self.habitat_out(d.habitat), pet_name=pets.get(d.habitat.pet_id),
                shared=d.id in shared_ids,
            ))
        return DesignListOut(items=items, total=total, page=page, page_size=page_size)

    @staticmethod
    def title_of(design: Design) -> str:
        if design.title:
            return design.title
        first = design.versions[0] if design.versions else None
        return make_title(first.prompt) if first is not None else "맞춤 설계"

    def get_version(self, db: Session, design: Design, version: int | None,
                    allowed: set[int] | None = None) -> DesignVersion:
        """버전을 찾는다. allowed 가 있으면 그 버전만 (지정하지 않으면 그중 최신)."""
        versions = [v for v in design.versions if allowed is None or v.version in allowed]
        if not versions:
            raise NotFoundError("설계 버전이 없습니다.")
        if version is None:
            return versions[-1]
        for v in versions:
            if v.version == version:
                return v
        raise NotFoundError(f"버전 {version} 을(를) 찾을 수 없습니다.")

    def design_out(self, db: Session, design: Design, v: DesignVersion, user: User | None) -> DesignOut:
        # 뷰어 메시 URL 에 지금 형상 코드의 지문을 붙인다: 배포로 형상이 바뀌면 URL 도 바뀌어 브라우저 캐시
        # (max-age 하루)가 옛 형상을 보여주지 않는다
        g = geometry_fingerprint((it["template"] for it in v.items), self.rules.printing)[:16]
        items = [
            ItemOut(
                index=it["index"], template=it["template"], label_ko=it["label_ko"], params=it["params"],
                reason_ko=it["reason_ko"],
                placement=PlacementOut(**it["placement"]) if it["placement"] else None,
                size_mm=it["size_mm"], print_size_mm=it["print_size_mm"],
                mesh_url=(f"/designs/{design.id}/versions/{v.version}/parts/{it['index']}.stl?g={g}"
                          if it["placement"] else None),
            )
            for it in v.items
        ]
        report = dict(v.report)
        stored_issues = report.get("issues", [])
        # 저장 뒤에 더한 기준을 넘는 값은 경고로만 덧붙인다 (저장된 보고서·통과 여부·내려받기는 그대로)
        issues = stored_issues + self._rule_notices(design, v, stored_issues)
        errors = _unresolved_errors(issues)
        validation = {
            "passed": v.passed,
            "summary": {
                "errors": len(errors),
                "warnings": sum(1 for i in issues if i["severity"] == "warning"),
                "auto_fixed": sum(1 for i in issues if i.get("auto_fixed")),
            },
            "issues": issues,
        }
        shared = self.shared_versions(db, design.id)
        see_all = _can_view_all(design, user)
        return DesignOut(
            id=design.id,
            title=self.title_of(design),
            is_owner=user is not None and _can_edit(design, user),
            shared=bool(shared),
            shared_versions=shared,
            owner_nickname=design.owner.nickname if design.owner else None,
            habitat=self.habitat_out(design.habitat, owner_view=see_all),
            versions=[
                VersionSummary(version=x.version, prompt=x.prompt, passed=x.passed, provider=x.provider,
                               created_at=x.created_at)
                for x in design.versions if see_all or x.version in shared
            ],
            current=VersionOut(
                version=v.version, prompt=v.prompt, provider=v.provider,
                summary_ko=v.llm_spec.get("summary_ko", ""), notes_ko=v.llm_spec.get("notes_ko", []),
                items=items, validation=validation, export_allowed=_exportable(v),
                created_at=v.created_at,
            ),
        )

    def _rule_notices(self, design: Design, v: DesignVersion, stored_issues: list[dict]) -> list[dict]:
        """저장된 버전이 그 뒤에 더한 기준(blocking=False, 예: 터널 최대 길이)을 넘으면 rule_changed 경고로 알린다.

        보기 화면에서만 덧붙이고 저장하지 않는다. 검사하지 못하면(규칙에서 빠진 종·옛 파라미터) 조용히 건너뛴다:
        보기를 막을 까닭이 아니다."""
        seen = {(i.get("item_index"), (i.get("details") or {}).get("field"))
                for i in stored_issues if i.get("code") == "rule_changed"}
        try:
            rctx = self._engine_ctx(design.habitat).rule_ctx
        except KeyError:  # 규칙 파일에서 빠진 종·크기: 비교할 기준이 없다
            return []
        out: list[dict] = []
        for it in v.items:  # 구조물 하나를 검사하지 못해도 나머지는 알린다
            try:
                t = get_template(it["template"])
                notices = rule_change_notices(t, t.load_stored_params(it["params"]), rctx, it["index"], it["label_ko"])
            except Exception:
                log.warning("rule-change check skipped: design=%s v=%s item=%s", design.id, v.version,
                            it.get("index"), exc_info=True)
                continue
            out.extend(n.model_dump(mode="json") for n in notices
                       if (n.item_index, n.details.get("field")) not in seen)
        return out

    # ── 메시 / 내보내기 ──────────────────────────────────────

    def _version_dir(self, design_id: str, version: int) -> Path:
        return self.mesh_dir / design_id / f"v{version}"

    def _rebuild(self, design: Design, v: DesignVersion, it: dict) -> BuiltItem:
        """저장된 최종 파라미터·배치로 구조물 하나를 다시 만든다."""
        from app.domain import Placement, PlacementHint
        try:
            t = get_template(it["template"])
            built = build_item(it["index"], t, t.load_stored_params(it["params"]), PlacementHint(),
                               self.rules.printing)
        except Exception as e:  # 템플릿 삭제·파라미터 스키마 변경·형상 커널 오류
            log.exception("mesh regeneration failed: design=%s v=%s item=%s", design.id, v.version, it)
            raise MeshRegenerationError(
                "이 설계 버전의 형상을 다시 만들 수 없어요. 같은 요청으로 새 버전을 만들어 주세요."
            ) from e
        if it["placement"]:
            built.placement = Placement(**it["placement"])
        return built

    def _log_drift(self, design: Design, v: DesignVersion, changed: list[str]) -> None:
        """다시 검증하게 된 까닭을 경고로 남긴다: 저장된 해시와 다른 파일(과 형상 지문 변화), 또는 해시가 없는 옛 버전."""
        stored = v.geometry or {}
        current = geometry_fingerprint((it["template"] for it in v.items), self.rules.printing)
        if stored.get("files"):
            log.warning(
                "rebuilt geometry differs from the validated geometry: design=%s v=%s files=%s "
                "fingerprint %s -> %s; re-validating",
                design.id, v.version, ",".join(changed), stored.get("fingerprint"), current,
            )
        else:
            log.warning("no stored geometry digests (version predates them): design=%s v=%s; re-validating",
                        design.id, v.version)

    def _revalidate(self, design: Design, v: DesignVersion, items: list[BuiltItem]) -> None:
        """다시 만든 구조물 전체(items, index 순)를 저장된 배치 그대로 지금 기준으로 다시 검증한다.
        겹침·틈새는 구조물끼리 함께 봐야 하므로 items 에는 버전의 모든 구조물이 들어 있어야 한다.
        검증을 실행하지 못하면 MeshRegenerationError, 통과하지 못하면 결과를 기억해 두고 GeometryChangedError."""
        try:
            report = revalidate(items, self._engine_ctx(design.habitat))
        except Exception as e:  # 규칙 파일에서 종/크기가 빠짐, 검증 중 형상 오류 등 → 확인할 수 없으면 막는다
            log.exception("re-validation failed to run: design=%s v=%s", design.id, v.version)
            raise MeshRegenerationError(
                "이 설계 버전의 형상을 다시 검증할 수 없어요. 같은 요청으로 새 버전을 만들어 주세요."
            ) from e
        if not report.passed:
            errors = [i.model_dump(mode="json") for i in report.errors]
            log.warning("re-validation failed: design=%s v=%s codes=%s", design.id, v.version,
                        ",".join(sorted({e["code"] for e in errors})))
            self._geometry_blocked[(design.id, v.version)] = errors
            raise GeometryChangedError(errors)
        log.info("re-validation passed: design=%s v=%s", design.id, v.version)

    def _ensure_meshes(self, design: Design, v: DesignVersion) -> Path:
        """메시 캐시가 없으면(새 인스턴스·삭제 등) 저장된 최종 파라미터로 다시 만든다.

        먼저 파일이 빠진 구조물만 다시 만들고, 캐시에는 검증을 거친 형상만 둔다 (파일이 있으면 그대로 응답하므로):
          - 다시 만든 파일이 저장할 때 기록한 해시와 바이트 단위로 같으면 그대로 쓴다 (형상 생성은 결정적).
          - 다르거나 (배포 사이 템플릿 build()·테셀레이션 설정·형상 라이브러리 변경) 해시가 없는 옛 버전이면,
            까닭을 경고로 남기고(_log_drift) 파일이 남아 있던 구조물까지 다시 만들어 구조물 전체를 함께 다시
            검증한다(_revalidate). 통과하면 다시 만든 형상으로 캐시 전체를 맞추고(남아 있던 파일과 섞이지 않게),
            다시 만들거나 검증하지 못하면 아무 파일도 쓰지 않고 뷰어·내려받기 모두 409 로 막는다.
          - 처음부터 검증을 통과하지 못한 버전은 다시 검증하지 않는다. 내려받기는 이미 막혀 있고(export 의
            _exportable 확인), 메시는 어디가 문제인지 보여 주는 뷰어에만 쓰인다."""
        d = self._version_dir(design.id, v.version)

        def missing() -> list[dict]:
            return [it for it in v.items if not all((d / n).is_file() for n in _cache_names(it))]

        if not missing():
            return d
        # 컨테이너가 새로 뜨면 캐시가 비어 있어 여러 요청이 동시에 재생성을 시도할 수 있다.
        # 버전별 잠금으로 한 번만 만들고, 파일은 원자적으로 교체해 반쯤 쓰인 파일이 응답되지 않게 한다.
        with self._version_lock(design.id, v.version):
            blocked = self._geometry_blocked.get((design.id, v.version))
            if blocked is not None:
                raise GeometryChangedError(blocked)
            todo = missing()
            if not todo:
                return d
            rebuilt = {it["index"]: self._rebuild(design, v, it) for it in todo}
            files = _cache_files(rebuilt.values())
            expected = (v.geometry or {}).get("files") or {}
            changed = sorted(name for name, data in files.items() if expected.get(name) != file_digest(data))
            if changed and v.passed:
                self._log_drift(design, v, changed)
                # 남아 있던 파일의 구조물도 다시 만들어 전체를 함께 검증하고, 그 형상으로 캐시 전체를 맞춘다
                rest = [it for it in v.items if it["index"] not in rebuilt]
                for it in rest:
                    rebuilt[it["index"]] = self._rebuild(design, v, it)
                self._revalidate(design, v, [rebuilt[i] for i in sorted(rebuilt)])
                files.update(_cache_files(rebuilt[it["index"]] for it in rest))
            _write_cache(d, files)
        return d

    def part_mesh_path(self, db: Session, design_id: str, version: int, index: int, user: User | None) -> Path:
        design, allowed = self.get_visible(db, design_id, user)
        v = self.get_version(db, design, version, allowed)
        if not any(it["index"] == index and it["placement"] for it in v.items):
            raise NotFoundError("해당 구조물 메시가 없습니다.")
        return self._ensure_meshes(design, v) / _world_name(index)

    def export(self, db: Session, design_id: str, version: int | None, fmt: str, user: User | None) -> ExportFile:
        import trimesh

        from app.geometry.export import ExportPart
        design, allowed = self.get_visible(db, design_id, user)
        v = self.get_version(db, design, version, allowed)
        if not _exportable(v):
            errors = _unresolved_errors(v.report.get("issues", []))
            raise ExportBlockedError(
                "검증을 통과하지 못한 설계는 내려받을 수 없습니다. 아래 문제를 해결하도록 설계를 수정해 주세요.",
                errors,
            )
        d = self._ensure_meshes(design, v)
        parts = [
            ExportPart(f"part{it['index'] + 1}_{it['template']}",
                       trimesh.load(d / _print_name(it["index"]), file_type="stl"))
            for it in v.items
        ]
        return export_parts(parts, fmt, f"nestforge_{design.id[:8]}_v{v.version}", self.rules.printing.plate_spacing_mm)
