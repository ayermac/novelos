"""Title contract helpers for keeping generated fiction aligned with the book title."""

from __future__ import annotations

from typing import Any


IMMORTAL_KEYWORDS = ("仙帝", "仙尊", "修仙", "仙界", "渡劫", "灵气", "元婴", "金丹")
URBAN_KEYWORDS = ("都市", "城市", "现代", "公司", "集团", "豪门", "大学", "医院", "商业")
MISMATCH_KEYWORDS = ("迷雾", "浓雾", "灯塔", "小镇", "长老会", "艾伦", "防空洞")


def infer_required_title_anchors(project: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Infer non-negotiable story anchors from the project title and genre."""
    project = project or {}
    title = str(project.get("name") or "")
    genre = str(project.get("genre") or "")
    anchors: list[dict[str, Any]] = []

    if "仙帝" in title:
        anchors.append({
            "key": "immortal_emperor",
            "label": "仙帝身份/修仙力量",
            "keywords": IMMORTAL_KEYWORDS,
            "rule": "主角必须具有仙帝级过往、归来/重生/降临等身份反差，核心冲突围绕修仙力量在现代社会展开。",
        })

    if "都市" in title or genre.lower() in {"urban", "都市", "都市修仙", "都市爽文"}:
        anchors.append({
            "key": "urban_stage",
            "label": "现代都市舞台",
            "keywords": URBAN_KEYWORDS,
            "rule": "主要舞台必须是现代城市社会，包含家族、商业、校园、医院、公司或豪门等都市网文场景。",
        })

    if "绝世" in title:
        anchors.append({
            "key": "power_fantasy",
            "label": "绝世强者爽点",
            "keywords": ("绝世", "强者", "碾压", "打脸", "身份反差", "归来"),
            "rule": "叙事必须保留强者归来、身份反差、打脸升级和压迫感释放的爽文结构。",
        })

    return anchors


def build_title_contract(project: dict[str, Any] | None) -> str:
    """Build prompt text that binds generation to the title promise."""
    project = project or {}
    title = str(project.get("name") or "未命名")
    genre = str(project.get("genre") or "未指定")
    description = str(project.get("description") or "")
    anchors = infer_required_title_anchors(project)

    lines = [
        "【书名契约】",
        f"书名: 《{title}》",
        f"类型: {genre}",
    ]
    if description:
        lines.append(f"项目简介: {description}")

    if anchors:
        lines.append("硬性锚点:")
        for anchor in anchors:
            lines.append(f"- {anchor['label']}: {anchor['rule']}")
    else:
        lines.append("硬性锚点: 所有设定、角色、大纲和章节必须服务于书名承诺，不得生成与书名无关的通用模板。")

    lines.extend([
        "一致性要求:",
        "- 世界观、主角身份、主要矛盾、章节事件必须能让读者一眼看出这是这本书，而不是另一本通用故事。",
        "- 不得把项目改写成与书名无关的封闭小镇、迷雾灯塔、末日悬疑或西式角色故事，除非书名/简介明确要求。",
    ])
    return "\n".join(lines)


def evaluate_title_alignment(
    project: dict[str, Any] | None,
    context_items: list[str],
) -> dict[str, Any]:
    """Evaluate whether existing project context satisfies inferred title anchors."""
    anchors = infer_required_title_anchors(project)
    text = "\n".join(item for item in context_items if item)
    if not anchors or not text.strip():
        return {
            "aligned": True,
            "required": [a["key"] for a in anchors],
            "missing": [],
            "mismatch_signals": [],
        }

    missing: list[str] = []
    for anchor in anchors:
        if not any(keyword in text for keyword in anchor["keywords"]):
            missing.append(anchor["key"])

    mismatch_signals = [keyword for keyword in MISMATCH_KEYWORDS if keyword in text]
    return {
        "aligned": len(missing) == 0,
        "required": [a["key"] for a in anchors],
        "missing": missing,
        "mismatch_signals": mismatch_signals,
    }
