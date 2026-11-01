from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.auth import require_admin

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


@router.get("/species", summary="등록 가능한 종·크기 목록 (규칙 파일 기준)", dependencies=[Depends(require_admin)])
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
                    }
                    for skey, s in sp.sizes.items()
                ],
            }
            for key, sp in rules.species_file.species.items()
        ],
    }
