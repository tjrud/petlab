from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["메타"])


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
                "sizes": [
                    {
                        "key": skey,
                        "display_name": s.display_name,
                        "max_recommended_count": s.max_recommended_count,
                        "count_warning_ko": s.count_warning_ko,
                        "enclosure_min_floor_mm": list(s.enclosure_min_floor_mm),
                        # 가상 케이지 배치 검토(끼임 틈·출입구 앞 공간·오르는 높이)에 쓰는 규칙 값
                        "layout_rules": {
                            "gap_safe_max_mm": s.gap_trap.safe_max_mm,
                            "gap_passable_min_mm": s.gap_trap.passable_min_mm,
                            "entrance_min_diameter_mm": s.entrance_min_diameter_mm,
                            "tunnel_min_inner_diameter_mm": s.tunnel_min_inner_diameter_mm,
                            "max_climb_height_mm": s.max_climb_height_mm,
                            "max_step_height_mm": s.max_step_height_mm,
                            "hideout_min_entrances": s.hideout_min_entrances,
                            "sand_bath_min_inner_mm": list(s.sand_bath_min_inner_mm),
                            "enclosure_min_floor_mm": list(s.enclosure_min_floor_mm),
                        },
                    }
                    for skey, s in sp.sizes.items()
                ],
            }
            for key, sp in rules.species_file.species.items()
        ],
    }
