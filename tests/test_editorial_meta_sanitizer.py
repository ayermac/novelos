from novel_factory.validators.editorial_meta import (
    is_editorial_meta_paragraph,
    strip_editorial_meta_blocks,
)


def test_strip_editorial_meta_removes_hook_advisory_paragraph():
    content = (
        "（章末钩子强度不足，当前钩子仅为“走”字及前往黑市的悬念。建议："
        "在陆恒戴上铭牌时增加一句环境暗示。但此处未扩写，保持原样。）\n\n"
        "深夜，江海城东郊，废弃的地下排水渠早已被改造成另一重天地。"
    )

    cleaned, removed = strip_editorial_meta_blocks(content)

    assert len(removed) == 1
    assert "章末钩子强度不足" not in cleaned
    assert cleaned.startswith("深夜，江海城东郊")


def test_strip_editorial_meta_preserves_story_parenthetical_and_system_suggestion():
    content = (
        "陆恒停在门口（这地方比传闻里更冷）。\n\n"
        "定位住户时数据被篡改，系统建议忽略，但他没有照做。"
    )

    cleaned, removed = strip_editorial_meta_blocks(content)

    assert removed == []
    assert cleaned == content
    assert is_editorial_meta_paragraph("陆恒停在门口（这地方比传闻里更冷）。") is False


def test_strip_editorial_meta_removes_inline_hook_advisory_segment():
    content = (
        "陆恒把铭牌扣进掌心，沿着楼梯向下走。"
        "（章末钩子强度不足，当前钩子仅为“走”字。建议：增加环境暗示。）"
        "\n\n楼道灯光在身后熄灭。"
    )

    cleaned, removed = strip_editorial_meta_blocks(content)

    assert len(removed) == 1
    assert "章末钩子强度不足" not in cleaned
    assert "陆恒把铭牌扣进掌心" in cleaned
    assert "楼道灯光在身后熄灭" in cleaned
