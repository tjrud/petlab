from __future__ import annotations

from fastapi import APIRouter, Request

from app.rules.loader import SizeRules

router = APIRouter(tags=["메타"])


def _list_or_none(v) -> list | None:
    """규칙 파일에서 null 일 수 있는 [가로, 세로] 값 (어항 크기 구분에는 바닥·모래목욕통 기준이 없을 수 있다)."""
    return list(v) if v is not None else None


@router.get("/health", summary="상태 확인")
def health(request: Request) -> dict:
    rules = request.app.state.rules
    settings = request.app.state.settings
    return {
        "status": "ok",
        "llm_provider": settings.resolved_llm_provider,
        "llm_ready": request.app.state.llm_config_error is None,
        "auth_enabled": settings.auth_enabled,
        "auth_ready": settings.auth_mode != "misconfigured",
        "email_verification": settings.email_mode,   # disabled | enabled | misconfigured
        "captcha": settings.captcha_mode,
        "database": {
            "dialect": request.app.state.db_dialect,
            "persistent": not request.app.state.db_ephemeral,
        },
        "rules": {
            "species_version": rules.species_file.version,
            "species_reviewed": rules.species_file.reviewed,
            "printing_version": rules.printing.version,
        },
    }


@router.get("/species", summary="등록 가능한 종·크기 목록 (규칙 파일 기준, 누구나)")
def species(request: Request) -> dict:
    rules = request.app.state.rules
    return {
        "rules_reviewed": rules.species_file.reviewed,
        "llm_provider": request.app.state.settings.resolved_llm_provider,
        "storage_persistent": not request.app.state.db_ephemeral,
        "species": [
            {
                "key": key,
                "display_name": sp.display_name,
                "sizes": [_size_out(skey, s, sp.habitat) for skey, s in sp.sizes.items()],
                # 사육 환경 (cage: 케이지 / aquarium: 어항). 어항이면 사육 환경의 높이는 물 깊이(바닥재 위~수면)다
                "habitat": sp.habitat,
                "templates": list(sp.allowed_templates),  # 이 종에 만들 수 있는 구조물 (템플릿 키)
                "max_count": sp.max_count,                # 입력할 수 있는 최대 마릿수
                "print_notes_ko": list(sp.print_notes_ko),  # 출력·설치 안내 (영어 요청이면 항목마다 번역)
                "size_hint_ko": sp.size_hint_ko,            # 크기 구분을 고를 때 보일 안내 (없으면 null)
            }
            for key, sp in rules.species_file.species.items()
        ],
    }


def _size_out(key: str, s: SizeRules, habitat: str) -> dict:
    return {
        "key": key,
        "display_name": s.display_name,
        # 권장 최대 마릿수와 경고 (없으면 null)
        "max_recommended_count": s.max_recommended_count,
        "count_warning_ko": s.count_warning_ko,
        "enclosure_min_floor_mm": _list_or_none(s.enclosure_min_floor_mm),  # 없으면 null (바닥 기준이 없는 크기)
        # 가상 케이지 배치 검토(끼임 틈·출입구 앞 공간·오르는 높이)에 쓰는 규칙 값. 가상 케이지는 케이지 종만 → 어항은 null
        "layout_rules": _layout_rules(s) if habitat == "cage" else None,
        # 권장 최소 마릿수와 경고 (없으면 null)
        "min_recommended_count": s.min_recommended_count,
        "min_count_warning_ko": s.min_count_warning_ko,
        # 어항 기준 (수조 부피 어림·구조물 위 물 깊이 등). 케이지 종은 null
        "aquatic": s.aquatic.model_dump(mode="json") if s.aquatic is not None else None,
    }


def _layout_rules(s: SizeRules) -> dict:
    return {
        "gap_safe_max_mm": s.gap_trap.safe_max_mm,
        "gap_passable_min_mm": s.gap_trap.passable_min_mm,
        "entrance_min_diameter_mm": s.entrance_min_diameter_mm,
        "tunnel_min_inner_diameter_mm": s.tunnel_min_inner_diameter_mm,
        "tunnel_max_length_mm": s.tunnel_max_length_mm,
        "max_climb_height_mm": s.max_climb_height_mm,
        "max_step_height_mm": s.max_step_height_mm,
        # 혼자 키울 때 / 여러 마리를 함께 키울 때 은신처 출입구 최소 개수
        "hideout_min_entrances": s.hideout_min_entrances.single,
        "hideout_min_entrances_group": s.hideout_min_entrances.group,
        "sand_bath_min_inner_mm": _list_or_none(s.sand_bath_min_inner_mm),
        "enclosure_min_floor_mm": _list_or_none(s.enclosure_min_floor_mm),
    }
