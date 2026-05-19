# v6.6.16 Real Project Burn-in & Regression Closure - Focused Review

**Version**: 6.6.16  
**Date**: 2026-05-20

## Review Scope

1. 是否存在测试假绿
2. 是否真实跑了 chapter 1 → memory → publish → chapter 2
3. 是否所有关键 API 都有 domain_result
4. 是否 fallback/degraded 没有被成功态吞掉
5. 是否 `docs/superpowers/` 未被 git 跟踪
6. 是否没有真实 LLM 调用进入自动测试

## Findings

### P0 — None

### P1 — 手动 burn-in 脚本假绿 (FIXED)

**问题**: 初版 `scripts/burnin_real_project.py` 使用 demo seed 而不是《异常修正员》fixture，CLI 参数顺序错误时仍继续执行，且没有对 `chapter_status` / `run_id` / `domain_result` 做硬断言。
**影响**: 手动 burn-in 可能显示绿色摘要，但没有真正跑通真实项目链路。
**修复**: 脚本改为直接 `init_db + seed_burnin_project`，再通过 CLI 和 API 逐步断言 chapter 1、memory backfill、publish guard、chapter 2、run detail audit、timeline 语义。任一步失败都会退出非 0。

### P1 — 预置指令跳过 Planner 导致 memory_context_audit 消失 (FIXED)

**问题**: fixture 预置了 1-3 章指令，工作流会从 `planned + has_instruction` 直接进入 Screenwriter。v6.6.14 的 `memory_context_audit` 只在 Planner 中写入，导致 Chapter 2 的继承审计为空。
**影响**: 系统可以证明上一章记忆已提取，但无法证明下一章生成链路消费了这批上下文。
**修复**: 在 Screenwriter 节点前补写缺失的 `memory_context_audit` artifact，并在 run detail 中透出。`built_at_node` 标明该审计由 `screenwriter_node` 补写。

### P1 — API 错误路径缺少 domain_result (FIXED)

**问题**: memory backfill 和 publish 的部分错误响应仍只有旧式 `error.code/message`，没有 `error.details.domain_result`。
**影响**: 前端/CLI 无法统一判断 blocked/failed/retryable，错误态可能退回字符串判断。
**修复**: 补齐 `CONFIRM_REQUIRED`、`RUN_NOT_FOUND`、`CHAPTER_NOT_FOUND`、`INVALID_STATUS`、`LLM_CONFIG_MISSING`、`MEMORY_CURATOR_FAILED`、`INTERNAL_ERROR`、`PUBLISH_FAILED` 等路径的 domain_result。

### P1 — CLI domain_result 缺失 (FIXED)

**问题**: `cmd_run_chapter` 直接输出 `run_with_graph` 的原始结果，不包含 `domain_result`。CLI 和 API 行为不一致。
**修复**: 新增 `_build_cli_domain_result()`，在 CLI JSON 输出中嵌入 domain_result。

### P2 — None

## Detailed Checks

### 1. 测试假绿检查 ✅

- `test_chapter1_has_domain_result`: 验证 CLI JSON 输出中 `data.domain_result` 非空
- `test_chapter1_domain_result_not_fake_green_for_fallback`: 验证 fallback/degraded 时 severity != "success"
- `test_memory_status_not_trusted_when_no_trusted_batch`: 验证无 trusted batch 时不误报
- `test_memory_curator_not_fake_green`: 验证 memory_curator 不假成功

所有 29 个测试都验证了具体行为而非仅 mock 路径。

### 2. 真实链路检查 ✅

ch1 → ch2 链路实际通过 `_run_chapter()` 调用 CLI subprocess，非 mock import。

### 3. Domain result 覆盖 ✅

- CLI `run-chapter --json`: `data.domain_result` ✅ (v6.6.16 修复)
- API `POST /run/chapter`: `data.domain_result` ✅ (v6.6.12)
- API `GET /runs/{run_id}`: `data.domain_result` ✅ (v6.6.10)
- API `POST /runs/{run_id}/memory/backfill` error paths: `error.details.domain_result` ✅
- API `POST /publish/chapter` error paths: `error.details.domain_result` ✅

### 4. fallback/degraded 语义 ✅

- `test_chapter1_domain_result_not_fake_green_for_fallback` 通过
- `test_memory_curator_not_fake_green` 通过

### 5. `docs/superpowers/` ✅

- `git ls-files docs/superpowers/` 返回空
- 测试 `test_docs_superpowers_not_in_git` 通过

### 6. 无真实 LLM 调用 ✅

- 所有自动测试使用 `--llm-mode stub`
- 手动脚本 `burnin_real_project.py` 默认 stub，real mode 需显式 opt-in
- `NOVEL_FACTORY_DISABLE_DOTENV=1` 在所有测试中设置

## Summary

All checks passed. Release is ready.
