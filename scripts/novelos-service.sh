#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/.service"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8765}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-5173}"
DB_PATH="${DB_PATH:-acceptance_novel_factory.db}"
CONFIG_PATH="${CONFIG_PATH:-config/local.yaml}"
LLM_MODE="${LLM_MODE:-real}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

API_PID_FILE="${RUNTIME_DIR}/api.pid"
WEB_PID_FILE="${RUNTIME_DIR}/web.pid"
API_LOG_FILE="${RUNTIME_DIR}/api.log"
WEB_LOG_FILE="${RUNTIME_DIR}/web.log"

usage() {
  cat <<EOF
Usage:
  scripts/novelos-service.sh start [api|web|all]
  scripts/novelos-service.sh stop [api|web|all]
  scripts/novelos-service.sh restart [api|web|all]
  scripts/novelos-service.sh status [api|web|all]
  scripts/novelos-service.sh logs [api|web|all]

Environment overrides:
  API_HOST=${API_HOST}
  API_PORT=${API_PORT}
  WEB_HOST=${WEB_HOST}
  WEB_PORT=${WEB_PORT}
  DB_PATH=${DB_PATH}
  CONFIG_PATH=${CONFIG_PATH}
  LLM_MODE=${LLM_MODE}
  PYTHON_BIN=${PYTHON_BIN}

Examples:
  scripts/novelos-service.sh restart
  LLM_MODE=stub scripts/novelos-service.sh start api
  tail -f .service/api.log .service/web.log
EOF
}

ensure_runtime_dir() {
  mkdir -p "${RUNTIME_DIR}"
}

pid_is_alive() {
  local pid="${1:-}"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

read_pid() {
  local file="$1"
  if [[ -f "${file}" ]]; then
    tr -d '[:space:]' < "${file}"
  fi
}

port_pid() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-30}"
  local port="${4:-}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      echo "${label} ready: ${url}"
      return 0
    fi
    if [[ -n "${port}" && -n "$(port_pid "${port}")" ]]; then
      echo "${label} listening on port ${port}; HTTP health check unavailable"
      return 0
    fi
    sleep 1
  done
  echo "${label} did not become ready: ${url}" >&2
  return 1
}

api_command() {
  local cmd=(
    "${PYTHON_BIN}" -m novel_factory.cli api
    --host "${API_HOST}"
    --port "${API_PORT}"
    --db-path "${DB_PATH}"
    --llm-mode "${LLM_MODE}"
  )
  if [[ -n "${CONFIG_PATH}" && -f "${ROOT_DIR}/${CONFIG_PATH}" ]]; then
    cmd+=(--config "${CONFIG_PATH}")
  fi
  printf '%q ' "${cmd[@]}"
}

start_api() {
  ensure_runtime_dir
  local pid
  pid="$(read_pid "${API_PID_FILE}")"
  if pid_is_alive "${pid}"; then
    echo "API already running (pid ${pid})"
    return 0
  fi

  local existing
  existing="$(port_pid "${API_PORT}")"
  if [[ -n "${existing}" ]]; then
    echo "API port ${API_PORT} is already in use (pid ${existing}); treating as running"
    echo "${existing}" > "${API_PID_FILE}"
    return 0
  fi

  echo "Starting API on http://${API_HOST}:${API_PORT}"
  (
    cd "${ROOT_DIR}"
    nohup bash -lc "$(api_command)" > "${API_LOG_FILE}" 2>&1 &
    echo $! > "${API_PID_FILE}"
  )
  wait_for_url "http://${API_HOST}:${API_PORT}/api/health" "API" 30 "${API_PORT}"
}

start_web() {
  ensure_runtime_dir
  local pid
  pid="$(read_pid "${WEB_PID_FILE}")"
  if pid_is_alive "${pid}"; then
    echo "WebUI already running (pid ${pid})"
    return 0
  fi

  local existing
  existing="$(port_pid "${WEB_PORT}")"
  if [[ -n "${existing}" ]]; then
    echo "WebUI port ${WEB_PORT} is already in use (pid ${existing}); treating as running"
    echo "${existing}" > "${WEB_PID_FILE}"
    return 0
  fi

  echo "Starting WebUI on http://${WEB_HOST}:${WEB_PORT}"
  (
    cd "${ROOT_DIR}/frontend"
    nohup npm run dev -- --host "${WEB_HOST}" --port "${WEB_PORT}" > "${WEB_LOG_FILE}" 2>&1 &
    echo $! > "${WEB_PID_FILE}"
  )
  wait_for_url "http://${WEB_HOST}:${WEB_PORT}/" "WebUI" 30 "${WEB_PORT}"
}

stop_by_pid_or_port() {
  local label="$1"
  local pid_file="$2"
  local port="$3"
  local pid
  pid="$(read_pid "${pid_file}")"

  if ! pid_is_alive "${pid}"; then
    pid="$(port_pid "${port}")"
  fi

  if [[ -z "${pid}" ]]; then
    echo "${label} is not running"
    rm -f "${pid_file}"
    return 0
  fi

  echo "Stopping ${label} (pid ${pid})"
  kill "${pid}" >/dev/null 2>&1 || true
  local i
  for ((i = 1; i <= 10; i++)); do
    if ! pid_is_alive "${pid}"; then
      rm -f "${pid_file}"
      echo "${label} stopped"
      return 0
    fi
    sleep 1
  done

  echo "${label} did not stop gracefully; sending SIGKILL"
  kill -9 "${pid}" >/dev/null 2>&1 || true
  rm -f "${pid_file}"
}

stop_api() {
  stop_by_pid_or_port "API" "${API_PID_FILE}" "${API_PORT}"
}

stop_web() {
  stop_by_pid_or_port "WebUI" "${WEB_PID_FILE}" "${WEB_PORT}"
}

status_one() {
  local label="$1"
  local pid_file="$2"
  local port="$3"
  local url="$4"
  local pid
  pid="$(read_pid "${pid_file}")"
  if ! pid_is_alive "${pid}"; then
    pid="$(port_pid "${port}")"
  fi

  if [[ -n "${pid}" ]]; then
    if curl -fsS "${url}" >/dev/null 2>&1; then
      echo "${label}: running / healthy (pid ${pid}, ${url})"
    else
      echo "${label}: running / listening (pid ${pid}, health check unavailable: ${url})"
    fi
  else
    echo "${label}: stopped"
  fi
}

status_api() {
  status_one "API" "${API_PID_FILE}" "${API_PORT}" "http://${API_HOST}:${API_PORT}/api/health"
}

status_web() {
  status_one "WebUI" "${WEB_PID_FILE}" "${WEB_PORT}" "http://${WEB_HOST}:${WEB_PORT}/"
}

show_logs() {
  local target="$1"
  case "${target}" in
    api)
      tail -n 80 "${API_LOG_FILE}" 2>/dev/null || echo "No API log yet: ${API_LOG_FILE}"
      ;;
    web)
      tail -n 80 "${WEB_LOG_FILE}" 2>/dev/null || echo "No WebUI log yet: ${WEB_LOG_FILE}"
      ;;
    all)
      echo "== API log =="
      tail -n 80 "${API_LOG_FILE}" 2>/dev/null || echo "No API log yet: ${API_LOG_FILE}"
      echo
      echo "== WebUI log =="
      tail -n 80 "${WEB_LOG_FILE}" 2>/dev/null || echo "No WebUI log yet: ${WEB_LOG_FILE}"
      ;;
    *)
      usage
      exit 2
      ;;
  esac
}

run_target() {
  local action="$1"
  local target="$2"
  case "${action}:${target}" in
    start:api) start_api ;;
    start:web) start_web ;;
    start:all) start_api; start_web ;;
    stop:api) stop_api ;;
    stop:web) stop_web ;;
    stop:all) stop_web; stop_api ;;
    restart:api) stop_api; start_api ;;
    restart:web) stop_web; start_web ;;
    restart:all) stop_web; stop_api; start_api; start_web ;;
    status:api) status_api ;;
    status:web) status_web ;;
    status:all) status_api; status_web ;;
    logs:api|logs:web|logs:all) show_logs "${target}" ;;
    *) usage; exit 2 ;;
  esac
}

main() {
  local action="${1:-status}"
  local target="${2:-all}"

  case "${action}" in
    start|stop|restart|status|logs)
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac

  case "${target}" in
    api|web|all)
      ;;
    frontend)
      target="web"
      ;;
    *)
      usage
      exit 2
      ;;
  esac

  run_target "${action}" "${target}"
}

main "$@"
