"""초안 미리보기 (설계 §8 preview): 사용 자세 STL, 출력 파트 STL, 한 장짜리 그림(sheet.png), info.json.

개발자 에이전트가 sheet.png 를 Read 도구로 열어 형상을 눈으로 확인한다. 그림은 matplotlib(Agg)로 그린다: 등각·위·앞·옆
네 방향과 출력 파트마다 출력 자세 하나. 연결 지점은 화살표(법선), 받침면(mount)은 사각형, 출입구는 굵은 빨간 화살표.

matplotlib 은 개발용이다 (서버 이미지에는 없다). 설치되어 있지 않으면 sheet.png 만 건너뛰고 이유를 알린다
(`uv run --with matplotlib python -m app.library preview …` 로 돌리면 된다).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.library import index


@dataclass
class PreviewResult:
    out_dir: Path
    files: list[Path] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)
    sheet_error: str | None = None


def _rules(rules: Any | None) -> Any:
    if rules is not None:
        return rules
    from app.config import get_settings
    from app.rules.loader import load_rules

    return load_rules(get_settings().rules_dir)


def _first_case(rules: Any, habitats: tuple[str, ...], species: str | None, size: str | None) -> tuple[str, str]:
    for sp_key, sp in rules.species_file.species.items():
        if sp.habitat not in habitats or (species is not None and sp_key != species):
            continue
        if size is None:
            return sp_key, next(iter(sp.sizes))
        if size in sp.sizes:
            return sp_key, size
        raise ValueError(f"{sp_key} has no size {size!r}; sizes: {', '.join(sp.sizes)}")
    raise ValueError(f"no species for habitats {habitats}" + (f" named {species!r}" if species else ""))


def anchor_kind(t: Any, p: Any, name: str, a: Any) -> str:
    if a.port is not None:
        return "door"
    if a.mount is not None:
        return "mount"
    if name in t.attach_order.get("slide", ()):
        return "slide"
    return "plain"


def _anchor_info(t: Any, p: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, a in t.anchors(p).items():
        d: dict[str, Any] = {"kind": anchor_kind(t, p, name, a), "origin": [round(float(x), 3) for x in a.origin],
                             "normal": [round(float(x), 3) for x in a.normal], "up": [round(float(x), 3) for x in a.up]}
        for k in ("port", "profile", "wall_mm", "side"):
            v = getattr(a, k, None)
            if v is not None:
                d[k] = v
        if a.mount is not None:
            d["mount"] = [round(float(x), 3) for x in a.mount]
        out[name] = d
    return out


def _features(t: Any, p: Any) -> dict[str, Any]:
    f = t.features(p)
    if hasattr(f, "model_dump"):
        return f.model_dump(mode="json")
    import dataclasses

    def plain(v: Any) -> Any:
        if dataclasses.is_dataclass(v):
            return {k: plain(x) for k, x in dataclasses.asdict(v).items()}
        if isinstance(v, (list, tuple)):
            return [plain(x) for x in v]
        if isinstance(v, dict):
            return {str(k): plain(x) for k, x in v.items()}
        if isinstance(v, (np.floating, np.integer)):
            return v.item()
        return v

    return plain(f)


def preview(data: Mapping[str, Any], *, params: Mapping[str, Any] | None = None, species: str | None = None,
            size: str | None = None, out_dir: Path | str | None = None, rules: Any | None = None,
            key: str | None = None) -> PreviewResult:
    """초안 dict → out_dir 에 use.stl, print_<key>.stl, sheet.png, info.json. params: 기본값 위에 덮어쓸 값."""
    from app.domain import PlacementHint
    from app.library.template import make_template, next_key
    from app.library.verify.variants import fit_ctx
    from app.services.engine import build_item
    from app.validation.autofix import clamp_params

    data = {k: v for k, v in dict(data).items() if not str(k).startswith("_")}
    family = str(data["family"])
    rules = _rules(rules)
    key = key or data.get("key") or next_key(family)
    t = make_template(data, key=key)
    sp, sz = _first_case(rules, tuple(data.get("habitats") or ("cage",)), species, size)
    ctx = fit_ctx(rules, sp, sz, 1)
    base = t.default_params(ctx).model_dump(mode="json")
    base.update(dict(params or {}))
    p = t.Params.model_validate(base)
    p, issues = clamp_params(t, p, ctx)
    out = Path(out_dir) if out_dir is not None else index.library_dir().parents[1] / "library_drafts" / "preview" / family
    out.mkdir(parents=True, exist_ok=True)
    res = PreviewResult(out)
    it = build_item(0, t, p, PlacementHint(), rules.printing)
    use = out / "use.stl"
    use.write_bytes(it.mesh.export(file_type="stl"))
    res.files.append(use)
    # 첫 출력 파트는 본체(it.print_mesh), 나머지는 it.parts[1:] (geometry.item_files 와 같은 순서)
    prints = [("body", it.print_mesh)] + [(pp.key, pp.print_mesh) for pp in it.parts[1:]]
    for pkey, pm in prints:
        f = out / f"print_{pkey}.stl"
        f.write_bytes(pm.export(file_type="stl"))
        res.files.append(f)
    built = t.build(p).bounding_box()
    raw_lo = np.array([built.min.X, built.min.Y, built.min.Z])
    info = {
        "key": key, "species": sp, "size": sz,
        "params": p.model_dump(mode="json"),
        "envelope": list(t.envelope(p)) if t.composable else None,
        "bbox": {"min": [round(float(x), 3) for x in raw_lo],
                 "max": [round(float(built.max.X), 3), round(float(built.max.Y), 3), round(float(built.max.Z), 3)]},
        "anchors": _anchor_info(t, p),
        "features": _features(t, p),
        "issues": [{"code": i.code, "message": i.message_ko, **({"details": i.details} if i.details else {})}
                   for i in issues] + [{"code": "rule_issue", "message": m} for m in t.rule_issues(p, ctx)],
        "constraints": [{"field": c.field, "min": c.min, "max": c.max, "source": c.source, "reason": c.reason_ko}
                        for c in t.constraints(p, ctx)],
    }
    info_path = out / "info.json"
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    res.files.append(info_path)
    res.info = info
    try:
        sheet = draw_sheet(t, p, t.build(p), prints, out / "sheet.png", title=f"{key}  {sp}/{sz}")
        res.files.append(sheet)
    except ImportError as e:
        res.sheet_error = (f"sheet.png skipped: {e}. Run with `uv run --with matplotlib python -m app.library "
                           "preview …`")
    return res


# ── 그림 ──

def _mesh_of(solid: Any) -> Any:
    from app.geometry.mesh import part_to_mesh

    return part_to_mesh(solid)


def _draw_mesh(ax: Any, mesh: Any, color: str = "#c8a27a") -> None:
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    tris = mesh.vertices[mesh.faces]
    light = np.array([0.4, -0.6, 0.7])
    light /= np.linalg.norm(light)
    shade = 0.45 + 0.55 * np.clip(mesh.face_normals @ light, 0, 1)
    base = np.array([int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)])
    colors = np.clip(base[None, :] * shade[:, None], 0, 1)
    coll = Poly3DCollection(tris, facecolors=colors, edgecolors="none", linewidths=0)
    ax.add_collection3d(coll)
    lo, hi = mesh.bounds
    _equal(ax, lo, hi)


def _equal(ax: Any, lo: np.ndarray, hi: np.ndarray, pad: float = 12.0) -> None:
    c = (lo + hi) / 2
    r = float(max(hi - lo)) / 2 + pad
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1))


def _draw_anchors(ax: Any, t: Any, p: Any, offset: np.ndarray) -> None:
    for name, a in t.anchors(p).items():
        o = np.asarray(a.origin, float) + offset
        n = np.asarray(a.normal, float)
        up = np.asarray(a.up, float)
        kind = anchor_kind(t, p, name, a)
        color = {"door": "#d62728", "mount": "#1f77b4", "slide": "#2ca02c"}.get(kind, "#555555")
        ax.quiver(*o, *(n * 18), color=color, linewidth=2.2 if kind == "door" else 1.4, arrow_length_ratio=0.25)
        ax.text(*(o + n * 22), name, color=color, fontsize=7)
        if a.mount is not None:
            tvec = np.cross(up, n)
            left, right, h = (float(x) for x in a.mount)
            corners = [o + tvec * left, o + tvec * right, o + tvec * right + up * h, o + tvec * left + up * h,
                       o + tvec * left]
            xs, ys, zs = zip(*corners, strict=True)
            ax.plot(xs, ys, zs, color=color, linewidth=1.2, linestyle="--")


VIEWS = (("iso", 25, -60), ("top", 90, -90), ("front", 0, -90), ("side", 0, 0))


def draw_sheet(t: Any, p: Any, solid: Any, prints: list[tuple[str, Any]], path: Path, title: str = "") -> Path:
    """2×3(출력 파트가 셋 이상이면 더 많은 칸) 그림: 등각·위·앞·옆(연결 지점 표시)과 출력 파트의 출력 자세."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mesh = _mesh_of(solid)
    n = len(VIEWS) + len(prints)
    cols = 3
    rows = max(2, -(-n // cols))
    fig = plt.figure(figsize=(cols * 4.2, rows * 4.0), dpi=110)
    color = getattr(t, "color", "#c8a27a") or "#c8a27a"
    for i, (label, elev, azim) in enumerate(VIEWS):
        ax = fig.add_subplot(rows, cols, i + 1, projection="3d")
        ax.set_proj_type("ortho")
        _draw_mesh(ax, mesh, color)
        _draw_anchors(ax, t, p, np.zeros(3))
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(label, fontsize=9)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")
        ax.tick_params(labelsize=6)
    for j, (pkey, pm) in enumerate(prints):
        ax = fig.add_subplot(rows, cols, len(VIEWS) + j + 1, projection="3d")
        ax.set_proj_type("ortho")
        _draw_mesh(ax, pm, color)
        ax.view_init(elev=20, azim=-60)
        ax.set_title(f"print {pkey} (bed z=0)", fontsize=9)
        ax.tick_params(labelsize=6)
    if n < rows * cols:  # 남는 칸: 파라미터 값
        ax = fig.add_subplot(rows, cols, n + 1)
        ax.axis("off")
        lines = [f"{k} = {v:g}" if isinstance(v, float) else f"{k} = {v}" for k, v in p.model_dump().items()]
        ax.text(0.0, 1.0, "params\n" + "\n".join(lines), va="top", ha="left", family="monospace", fontsize=8)
    if title:
        fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
