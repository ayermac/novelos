# v6.5.1 Interaction Primitives Report

## 总体结论

**PASS**

v6.5.0 完成交互体验规格收口，v6.5.1 完成交互基础组件和两个样板接入点。

## 交付内容

新增：

- `frontend/src/components/ui/Toast.tsx`
- `frontend/src/components/ui/LoadingButton.tsx`
- `frontend/src/components/ui/Skeleton.tsx`
- `frontend/src/components/ui/__tests__/interaction-primitives.test.tsx`
- `docs/codex/planning/novel-factory-v6.5-interaction-excellence-spec.md`

修改：

- `frontend/src/App.tsx`：全局挂载 `ToastProvider`
- `frontend/src/components/ui/index.ts`：导出新 primitives
- `frontend/src/components/ui/ui.css`：新增 toast/loading/skeleton/focus/reduced-motion 样式
- `frontend/src/pages/Onboarding.tsx`：项目创建接入 `LoadingButton`、toast、`InlineMessage`
- `frontend/src/components/project/QualityDiagnosisPanel.tsx`：质量诊断接入 skeleton、toast、`LoadingButton`
- `docs/codex/README.md`
- `docs/codex/planning/novel-factory-cross-platform-desktop-client-plan.md`

## 行为变化

- 创建项目时按钮进入明确 pending，并在成功/失败后给出 toast。
- 创建失败的页面内错误从自定义红色块改为统一 `InlineMessage`。
- 质量诊断首次展开时显示 skeleton，不再只有"正在诊断..."静态文本。
- 质量诊断支持"重新诊断"按钮，并在刷新成功/失败后给出 toast。
- Toast 在孤立测试场景下安全 no-op，不要求所有历史组件测试都包 provider。

## 已知限制

- 只接入两个样板页面，尚未全面替换 Overview / Chapter / Settings 的所有按钮。
- Toast 当前不支持 action button。
- Skeleton 是通用骨架，不含页面专属布局骨架。
- 页面级体验仍需 v6.5.2+ 继续推进。

## 验证结果

| 命令 | 结果 |
| --- | --- |
| `cd frontend && npm run typecheck` | 通过 |
| `cd frontend && npm run lint` | 通过 |
| `cd frontend && npm run build` | 通过（保留既有 chunk size warning） |
| `cd frontend && npm run test -- --run` | 14 files, 173 passed |
| `python3 scripts/verify.py smoke` | 27 passed |
