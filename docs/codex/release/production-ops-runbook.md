# Novelos 生产运维手册 (Production Ops Runbook)

版本: v6.6.20
日期: 2026-05-24

---

## 1. 备份

### 1.1 确认数据库位置

数据库文件位置取决于启动参数：

- **CLI / API 直接启动**: `--db-path` 参数指定
- **Service 脚本启动**: 默认 `acceptance_novel_factory.db`（项目根目录）
- **Desktop 客户端**: `~/Library/Application Support/novelos-desktop/data/novelos.db`（macOS）

```bash
# 检查 API health 中的 db path
curl -sS http://127.0.0.1:8765/api/health | python3 -m json.tool
# 或在启动日志中查看
```

### 1.2 需要备份的文件

| 文件/目录 | 说明 | 重要性 |
|-----------|------|--------|
| `.db` | 主 SQLite 数据库 | 必需 |
| `.db-wal` | WAL 日志（如使用 WAL 模式） | 必需（在线备份时） |
| `.db-shm` | 共享内存文件 | 必需（在线备份时） |
| `config/local.yaml` | 用户配置文件 | 高 |
| `config/*.yaml` | 其他配置文件 | 中 |
| `.env` | 环境变量/密钥 | 高（加密存储） |
| `desktop/release/` | 桌面客户端构建产物 | 低（可重建） |

### 1.3 备份方式

#### 推荐：SQLite 在线备份

```bash
# 先获取 DB 路径
DB_PATH="acceptance_novel_factory.db"

# 使用 SQLite backup API（最安全）
sqlite3 "${DB_PATH}" ".backup 'backup/novelos-$(date +%Y%m%d-%H%M%S).db'"
```

#### 替代：停服务后拷贝

```bash
# 1. 停服务
scripts/novelos-service.sh stop

# 2. 拷贝
BACKUP_DIR="backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "${BACKUP_DIR}"
cp "${DB_PATH}" "${BACKUP_DIR}/"
cp "${DB_PATH}-wal" "${BACKUP_DIR}/" 2>/dev/null || true
cp "${DB_PATH}-shm" "${BACKUP_DIR}/" 2>/dev/null || true
cp config/local.yaml "${BACKUP_DIR}/" 2>/dev/null || true

# 3. 启服务
scripts/novelos-service.sh start
```

#### 替代：直接拷贝（含 WAL checkpoint）

```bash
# 先 checkpoint WAL，再拷贝
sqlite3 "${DB_PATH}" "PRAGMA wal_checkpoint(TRUNCATE);"
cp "${DB_PATH}" "backup/novelos-$(date +%Y%m%d-%H%M%S).db"
```

### 1.4 备份频率建议

| 场景 | 频率 | 保留策略 |
|------|------|----------|
| 本地个人使用 | 每周一次 | 保留最近 4 个 |
| 活跃创作期 | 每日一次 | 保留最近 7 个 |
| 小团队/生产 | 每日自动 + 每次发布前 | 保留最近 30 个，每月归档 |

---

## 2. 恢复

### 2.1 停止 API/Desktop Sidecar

```bash
# 使用 service 脚本
scripts/novelos-service.sh stop

# 或手动查找并停止
lsof -tiTCP:8765 -sTCP:LISTEN | xargs kill 2>/dev/null || true

# Desktop: 退出应用，确认 sidecar 已停止
ps aux | grep novelos-sidecar | grep -v grep
```

### 2.2 恢复数据库

```bash
# 1. 确认服务已停止
scripts/novelos-service.sh status

# 2. 恢复 DB 文件
BACKUP_DB="backups/20260524-120000/novelos.db"
DB_PATH="acceptance_novel_factory.db"
cp "${BACKUP_DB}" "${DB_PATH}"

# 3. 如有 WAL/SHM，一并恢复
cp "${BACKUP_DB}-wal" "${DB_PATH}-wal" 2>/dev/null || true
cp "${BACKUP_DB}-shm" "${DB_PATH}-shm" 2>/dev/null || true
```

### 2.3 迁移健康检查

```bash
# 启动 API 后检查迁移状态
python3 -m novel_factory.cli doctor --json

# 或直接检查 health endpoint
scripts/release_smoke.py --api-url http://127.0.0.1:8765/api/health
```

### 2.4 Release Smoke 验证恢复

```bash
python3 scripts/release_smoke.py --api-url http://127.0.0.1:8765/api/health
```

### 2.5 版本回滚和迁移不可逆风险

- **SQLite 迁移是向前的**: 降级 DB 到新版本未识别的 schema 会导致错误
- **回滚策略**: 
  1. 用旧代码 + 旧备份启动
  2. 不要在新代码 + 旧 DB 上运行（除非验证兼容性）
  3. 如需降级，先恢复到升级前的备份

---

## 3. 故障诊断

### 3.1 Live API 版本不一致

**症状**: `/api/health` 返回的版本与源码不同

**排查步骤**:

```bash
# 1. 检查 health 返回的完整信息
curl -sS http://127.0.0.1:8765/api/health | python3 -m json.tool

# 2. 关注 startup 字段
#   - started_at: 进程启动时间
#   - source_root: 代码来源目录
#   - python: 使用的 Python 解释器
#   - cwd: 工作目录

# 3. 对比源码版本
python3 -c "from novel_factory.version import __version__; print(__version__)"

# 4. 查找运行中的进程
lsof -tiTCP:8765 -sTCP:LISTEN
ps aux | grep "novel_factory.cli api" | grep -v grep

# 5. 检查进程启动时间
ps -o pid,lstart,command -p <PID>

# 6. 如果进程启动时间早于源码修改时间，说明是旧进程
#    安全停止并重启
kill <PID>
scripts/novelos-service.sh start
```

### 3.2 端口被旧进程占用

```bash
# 查找占用端口的进程
lsof -tiTCP:8765 -sTCP:LISTEN

# 安全停止（先 SIGTERM，等待 10s，再 SIGKILL）
PID=$(lsof -tiTCP:8765 -sTCP:LISTEN | head -1)
if [ -n "$PID" ]; then
    kill "$PID"
    sleep 10
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
fi

# 重启
scripts/novelos-service.sh start
```

### 3.3 Real LLM 失败定位

```bash
# 1. 检查 API key
python3 -m novel_factory.cli config validate --json

# 2. 检查 provider 连接
python3 -m novel_factory.cli llm smoke --json

# 3. 检查 config 中的 provider/base_url/model
cat config/local.yaml | grep -E "provider|base_url|model"

# 4. 检查 timeout 设置
cat config/local.yaml | grep -i timeout

# 5. 查看 segment events（分段生成诊断）
curl -sS "http://127.0.0.1:8765/api/projects/{project_id}/chapters/{n}/events" | \
  python3 -m json.tool | grep -E "segment_|failed|error"

# 6. 查看 workflow run 最后状态
curl -sS "http://127.0.0.1:8765/api/projects/{project_id}/runs" | \
  python3 -m json.tool | head -50

# 7. 查看最后失败的节点日志
# 在 run detail 中查找 last_error 和 failed_node
```

### 3.4 Workflow 卡 Running

```bash
# 1. 检查 run health dashboard
curl -sS http://127.0.0.1:8765/api/runs/health | python3 -m json.tool

# 2. 检查特定项目的 production health
curl -sS "http://127.0.0.1:8765/api/projects/{project_id}/production/health-summary" | \
  python3 -m json.tool

# 3. 手动标记 stuck run
# （API 已有 /api/runs/health/mark-stuck 端点）

# 4. 如果确认卡住，可以重置
curl -sS -X POST "http://127.0.0.1:8765/api/projects/{project_id}/chapters/{n}/reset-recovery"
```

### 3.5 Desktop Sidecar 启动失败

**症状**: Desktop 应用显示 "sidecar failed" 或 "无法连接"

**排查步骤**:

```bash
# 1. 检查 desktop runtime status
# （在 desktop 开发者工具中查看）

# 2. 查看 sidecar 日志
tail -n 100 ~/Library/Application\ Support/novelos-desktop/logs/sidecar-stdout.log
tail -n 100 ~/Library/Application\ Support/novelos-desktop/logs/sidecar-stderr.log

# 3. 手动启动 sidecar 测试
python3 -m novel_factory.cli api \
    --host 127.0.0.1 \
    --port 57660 \
    --db-path ~/Library/Application\ Support/novelos-desktop/data/novelos.db \
    --llm-mode real

# 4. 检查 version mismatch
# desktop package.json 版本应与 API health 版本一致
cat desktop/package.json | grep version
curl -sS http://127.0.0.1:{sidecar_port}/api/health | python3 -m json.tool

# 5. 如果版本不一致，重新构建 desktop
# cd desktop && npm run build && npm run dist:mac
```

### 3.6 敏感信息处理

**禁止行为**:
- 不要把 API key 粘贴到 issue、log、截图中
- 不要把 `.env` 内容提交到 git
- 不要在公共频道分享 `config/local.yaml`（可能含 key）

**诊断包脱敏**:

```bash
# 创建诊断包前脱敏
tar czf diagnostics.tar.gz \
    --exclude="*.db" \
    --exclude=".env" \
    --exclude="config/local.yaml" \
    .service/api.log \
    .service/web.log \
    docs/codex/reports/

# 如需分享 config，先删除 key
cat config/local.yaml | sed 's/api_key:.*/api_key: "***REDACTED***"/g' > config-safe.yaml
```

---

## 4. 发布检查清单

### 4.1 发布前

```bash
# 1. 版本对齐检查
python3 scripts/release_smoke.py --json

# 2. 全量测试
python3 -m pytest -q

# 3. 前端检查
cd frontend && npm run typecheck && npm run lint && npm run build && npm test -- --run

# 4. 桌面检查
cd desktop && npm run typecheck && npm run build

# 5. 备份当前 DB
sqlite3 acceptance_novel_factory.db ".backup 'backup/pre-release-$(date +%Y%m%d).db'"
```

### 4.2 发布后验证

```bash
# 1. API health 版本正确
curl -sS http://127.0.0.1:8765/api/health | python3 -m json.tool

# 2. CLI 版本正确
python3 -m novel_factory.cli --version

# 3. Desktop build 成功
# （需要手动验证桌面应用启动和 sidecar 连接）

# 4. 关键用户流程 stub 验证
python3 scripts/burnin_real_project.py
```

---

## 5. 常用命令速查

| 任务 | 命令 |
|------|------|
| 启动 API | `scripts/novelos-service.sh start api` |
| 停止 API | `scripts/novelos-service.sh stop api` |
| 查看状态 | `scripts/novelos-service.sh status` |
| 查看日志 | `scripts/novelos-service.sh logs api` |
| 发布 smoke | `python3 scripts/release_smoke.py --json` |
| 备份 DB | `sqlite3 DB.db ".backup 'backup/name.db'"` |
| 迁移检查 | `python3 -m novel_factory.cli doctor --json` |
| LLM 连通性 | `python3 -m novel_factory.cli llm smoke --json` |
| 长章节 soak | `python3 scripts/soak_real_llm_long_chapter.py --llm-mode stub` |
| 真实 LLM soak | `python3 scripts/soak_real_llm_long_chapter.py --llm-mode real --config config/local.yaml` |
