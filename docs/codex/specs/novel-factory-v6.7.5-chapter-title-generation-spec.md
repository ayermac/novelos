# Novel Factory v6.7.5 Chapter Title Generation Specification

**Version**: 6.7.5  
**Status**: Implemented  
**Branch**: `codex-v6.7.5-chapter-title-generation`  
**Date**: 2026-05-26

---

## 1. Background

### 1.1 Problem Statement

In previous versions, when `AuthorOutput.title` was unusable (empty, placeholder, or invalid), the system derived chapter titles from the content opening text. This approach produced unattractive, uninformative titles that:
- Often captured mundane opening sentences
- Failed to highlight key plot elements
- Did not create reader intrigue
- Lacked narrative significance

### 1.2 Motivation

Chapter titles are critical for reader engagement. A good title should:
- Highlight key objects, locations, or events
- Create suspense or curiosity
- Signal important plot developments
- Stand alone as compelling hooks

The content-opening approach fundamentally fails these criteria because opening sentences are typically scene-setting prose, not narrative highlights.

---

## 2. Goals

### 2.1 Primary Goals

1. **Independent Title Generation**: Implement LLM-based title generation that derives titles from comprehensive chapter context, not just opening text.

2. **Title Quality Rules**: Enforce specific rules for generated titles:
   - 4-12 Chinese characters (max 16)
   - No punctuation
   - No planning verbs/terms
   - Not derived from content opening
   - Highlight key elements (objects, locations, countdown, doubts, crisis, hooks)

3. **Fallback Strategy**: Adjust fallback order to prioritize generated titles over content-opening derivation.

4. **Failure Resilience**: Title generation failures must NOT block the workflow.

5. **Plain Text Path Coverage**: Ensure plain-text fallback path also uses new title logic.

### 2.2 Non-Goals

- Modifying title generation for other agents (Planner, Screenwriter)
- Changing database schema for title storage
- Implementing title validation at publication time

---

## 3. Implementation Scope

### 3.1 Core Changes

#### 3.1.1 New Model: `TitleGenerationOutput`

**File**: `novel_factory/models/schemas.py`

```python
class TitleGenerationOutput(BaseModel):
    """v6.7.5: Structured output for chapter title generation."""
    title: str
    reasoning: str = ""
```

#### 3.1.2 New Methods in `AuthorAgent`

**File**: `novel_factory/agents/author.py`

1. **`_generate_chapter_title(state, instruction, content) -> str | None`**
   - Invokes LLM with structured prompt
   - Uses chapter content, instruction context, and scene beats
   - Returns `None` on failure (does not raise)
   - Only runs in `real` mode

2. **`_repair_or_generate_title(state, instruction, content, current_title) -> str | None`**
   - Called when existing title is opening-derived
   - In real mode: calls `_generate_chapter_title`
   - In stub mode: falls back to instruction-derived

3. **`_is_opening_derived_title(title, content, chapter_number) -> bool`**
   - Detects if title was derived from content opening
   - Used to trigger title repair

#### 3.1.3 Modified Method: `_derive_title`

**New Fallback Order**:

```
1. Existing usable title (from chapter)
   ↓ (if opening-derived, attempt repair)
2. Generated/repaired title (LLM-based, NEW)
   ↓
3. Instruction-derived title
   ↓
4. Explicit content heading (only if actual heading)
   ↓
5. "第N章"
```

**Key Change**: Content opening derivation (`_title_from_content_opening`) is **removed** from the primary fallback chain.

#### 3.1.4 Title Generation Prompt

The LLM prompt includes:
- Chapter number
- Instruction objective
- Key events
- Ending hook
- Plots to plant/resolve
- Content opening summary (first 200 chars)
- Content ending summary (last 200 chars)

**Title Rules in Prompt**:
```
1. 4-12个中文字符（最多16字）
2. 不要标点符号
3. 不要使用规划性动词或术语
4. 不要直接取自正文开头
5. 突出关键物品、地点、倒计时、疑点、危机、钩子等
```

### 3.2 Validation Rules

The existing `_is_usable_chapter_title` method enforces:
- No placeholders ("待命名", "未命名", "占位")
- No chapter number only ("第N章", "第N章节")
- No planning verbs (引入, 铺垫, 描绘, 建立, 推进, 承接, 完成, 解决, 展示, 呈现, 交代, 安排, 触发, 围绕)
- No planning terms (本章, 目标, 关键事件, 写作指令)
- No punctuation (，。；;)
- Max 16 characters for suffix

### 3.3 Failure Handling

Title generation failures are handled gracefully:
- `_generate_chapter_title` returns `None` on any exception
- Fallback chain continues to instruction-derived title
- Workflow is never blocked by title generation failure
- Logging captures failure details for debugging

---

## 4. Testing

### 4.1 Test File

**File**: `tests/test_v675_chapter_title_generation.py`

### 4.2 Test Categories

1. **Model Tests**: `TitleGenerationOutput` creation and validation
2. **Validation Tests**: `_is_usable_chapter_title` with various inputs
3. **Detection Tests**: `_is_opening_derived_title` accuracy
4. **Fallback Tests**: `_title_from_instruction` derivation
5. **Utility Tests**: `_clean_title_suffix`, `_strip_chapter_prefix`, `_instruction_items`
6. **Integration Tests**: Fallback chain behavior
7. **Compliance Tests**: Title rules validation

### 4.3 Test Coverage

- All new methods have unit tests
- Edge cases covered (empty input, None values, special characters)
- Fallback chain verified
- Failure resilience confirmed

---

## 5. Verification Commands

```bash
# Run all tests
python3 -m pytest tests/test_v675_chapter_title_generation.py -v

# Run full test suite
python3 -m pytest -q

# Verify version
python3 -c "from novel_factory.version import get_version; print(get_version())"
# Expected: 6.7.5

# Frontend checks
cd frontend && npm run typecheck && npm run lint && npm run build
```

---

## 6. Acceptance Criteria

- [x] `TitleGenerationOutput` model added to schemas
- [x] `_generate_chapter_title` method implemented in AuthorAgent
- [x] `_repair_or_generate_title` method implemented
- [x] `_is_opening_derived_title` method implemented
- [x] `_derive_title` fallback order updated
- [x] Content opening removed as primary title source
- [x] Title generation failure does not block workflow
- [x] Plain text path uses new title logic (via `_derive_title` call)
- [x] Test file created with comprehensive coverage
- [x] All tests pass
- [x] Version updated to 6.7.5
- [x] No lint errors

---

## 7. Migration Notes

### 7.1 Backward Compatibility

- Existing chapters with valid titles are preserved
- Opening-derived titles are detected and repaired in real mode
- Stub mode behavior unchanged (no LLM calls)

### 7.2 Performance Impact

- Title generation adds one LLM call in real mode when title is unusable
- Call is made only when necessary (title is invalid or opening-derived)
- Failure does not impact workflow performance

### 7.3 Database Impact

- No schema changes required
- Titles are stored in existing `chapters.title` column

---

## 8. Future Considerations

1. **Title Templates**: Consider configurable title templates per genre
2. **Title History**: Track title generation attempts for analysis
3. **Title Rating**: Allow user rating of generated titles for feedback
4. **Multi-title Options**: Generate multiple title options for user selection

---

## 9. References

- `novel_factory/agents/author.py`: Main implementation
- `novel_factory/models/schemas.py`: Output models
- `tests/test_v675_chapter_title_generation.py`: Test suite
- `CHANGELOG.md`: Version history
