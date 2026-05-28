# v6.7.7 Genesis Generation Progress Streaming Spec

## Problem Statement

Genesis generation (project bible creation) can take 30-120 seconds in real LLM mode, during which the frontend shows only a spinner with "AI 正在生成项目设定，请稍候...". Users have no visibility into:
- Which phase is currently running
- How many segments remain
- Whether the process is stuck or progressing

## Solution

Add SSE-based progress streaming to the Genesis generation pipeline.

### Backend

#### New Endpoints

**`POST /api/projects/{project_id}/genesis/generate/start`**
- Accepts the same `GenesisGenerateRequest` body as the sync endpoint
- Creates a `running` genesis run
- Returns `{ run_id, stream_url, status: "running" }`
- Kicks off background generation task

**`GET /api/projects/{project_id}/genesis/generate/stream/{run_id}`**
- Returns `text/event-stream` SSE response
- Pushes progress events in real-time
- Sends keepalive comments every 30s
- Terminal events: `genesis_completed` or `genesis_failed`

#### Progress Event Types

| Event | Data Fields | Description |
|-------|------------|-------------|
| `genesis_started` | `run_id` | Generation task started |
| `segment_started` | `segment`, `label` | A segment (foundation/cast/plot/instructions/repair/quality_report) started |
| `segment_completed` | `segment`, `label` | A segment completed |
| `chapter_start` | `chapter_start`, `chapter_end`, `label` | An instruction chunk started |
| `chapter_end` | `chapter_start`, `chapter_end`, `label` | An instruction chunk completed |
| `genesis_completed` | `genesis_run` | Full generation completed with final data |
| `genesis_failed` | `error` | Generation failed with error message |

#### Segment Display Labels

| Segment | Label |
|---------|-------|
| `foundation` | 正在生成基础设定 |
| `cast` | 正在生成角色与势力 |
| `plot` | 正在生成剧情大纲 |
| `instructions` | 正在生成章节指令 X-Y |
| `repair` | 正在校验设定完整性 |
| `quality_report` | 正在评估草案质量 |

#### Implementation Details

- In-memory `asyncio.Queue` per run for SSE event delivery
- Background `asyncio.Task` for non-blocking generation
- Progress callback threaded through `_generate_stub_draft`, `_generate_real_draft`, `_generate_real_draft_with_scaffold_fallback`
- Queue auto-cleanup after 5 seconds post-completion
- If a `running` Genesis row has no in-process queue on stream reconnect, the run is treated as interrupted and emits `genesis_failed`
- Status uses `generated` (not `completed`) for consistency with existing system

### Frontend

#### GenesisModule.tsx Changes

1. **Streaming-first approach**: `handleGenerate` calls the start endpoint first
2. **EventSource connection**: Connects to `stream_url` for real-time progress
3. **Step-by-step UI**: Shows checklist-style progress with icons:
   - Pending: gray dot
   - Running: spinning loader, blue text
   - Completed: green checkmark
   - Failed: red X
4. **Fallback**: If EventSource is unavailable or fails, falls back to existing polling

#### New State

```typescript
interface GenesisProgressStep {
  id: string
  segment: string
  label: string
  status: 'pending' | 'running' | 'completed' | 'failed'
}

interface GenesisProgressState {
  active: boolean
  runId: string | null
  streamUrl: string | null
  steps: GenesisProgressStep[]
  currentLabel: string
  error: string | null
}
```

### Backward Compatibility

- `POST /genesis/generate` (canonical body-style) — preserved, works as before
- `POST /projects/{id}/genesis/generate` (path-style) — preserved, works as before
- Frontend falls back to sync endpoint if start endpoint fails

### Testing

- 16 backend tests in `tests/test_v677_genesis_progress_streaming.py`
- Covers: start endpoint validation, SSE event ordering, interrupted running runs, error handling, backward compatibility
- 3 frontend tests in `frontend/src/components/project/__tests__/v677-genesis-progress-streaming.test.tsx`
- Covers: immediate progress surface, stream URL normalization, reconnect progress labels, and reconnect phase ordering

### Related Author Stability

During v6.7.7 validation, real-mode segmented Author generation also received a targeted stability fix:

- Segment merge removes repeated boundary paragraphs from adjacent Author segments.
- When the final Author segment misses the last scene beat or chapter `ending_hook`, Author retries only the final segment with explicit final-beat context.
- If the retry still fails the final-hook check, the quality gate remains blocking; no synthetic text is inserted to fake a pass.
