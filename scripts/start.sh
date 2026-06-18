#!/bin/bash
# start.sh — 一键启动 realtime-novel 前后端
#
# 端口约定（v0.6 起，hardcoded）：
# - 前端 dev server:  http://localhost:7777
# - 后端 API:         http://127.0.0.1:7778
# - API 代理：        前端 /api → 后端 7778（vite.config.ts 配）
#
# 调整端口：改下面 3 个常量 + 同步改 frontend/vite.config.ts + pyproject.toml
# 不要散落改，端口来源单一。

set -e

# ============ 配置 ============
FRONTEND_PORT=7777
BACKEND_PORT=7778
HOST=127.0.0.1

# FRIDAY 代理凭证（必需：v0.5+ 真实 LLM 链路需要）
# friday 平台只用一个 Bearer token (config.yaml 的 app_id 字段即 api_key)
# 启动前必须设环境变量：
#   export FRIDAY_API_KEY=21899390080843030554
# 脚本会检查，没设会报错退出

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
UVICORN="$PROJECT_ROOT/.venv/bin/uvicorn"
LOG_DIR="$PROJECT_ROOT/tmp/logs"
PID_DIR="$PROJECT_ROOT/tmp/pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

# ============ 前置检查 ============
check_env() {
    if [ -z "$FRIDAY_API_KEY" ]; then
        echo "❌ FRIDAY_API_KEY 环境变量未设置"
        echo "   启动 v0.5+ 真实 LLM 链路需要 friday 代理凭证"
        echo "   设置："
        echo "     export FRIDAY_API_KEY=21899390080843030554"
        exit 1
    fi
}

check_dependencies() {
    if [ ! -d "$PROJECT_ROOT/.venv" ]; then
        echo "❌ .venv 目录不存在，请先创建虚拟环境"
        exit 1
    fi
    if [ ! -d "$PROJECT_ROOT/frontend/node_modules" ]; then
        echo "❌ frontend/node_modules 不存在，请先 npm install"
        exit 1
    fi
}

# 杀端口占用进程（只杀本项目相关的）
# 判断: 进程 cmdline 包含 realtime_novel 或 vite --port 对应端口
kill_port_if_used() {
    local port=$1
    local name=$2
    # 找占用该端口的 PIDs
    local pids=$(lsof -nP -iTCP:$port -sTCP:LISTEN -t 2>/dev/null)
    if [ -z "$pids" ]; then
        return 0  # 端口空闲
    fi

    echo "⚠️  端口 $port ($name) 已被占用，尝试清理..."
    local killed=0
    local kept=0
    for pid in $pids; do
        # 取进程命令行
        local cmdline=$(ps -p $pid -o command= 2>/dev/null | tr -d '\n')
        if echo "$cmdline" | grep -qE "realtime_novel|realtime-novel.*vite|vite --port $port"; then
            echo "   kill PID $pid (realtime-novel 进程): $cmdline"
            kill $pid 2>/dev/null
            sleep 1
            # 还活着就 kill -9
            if kill -0 $pid 2>/dev/null; then
                kill -9 $pid 2>/dev/null
            fi
            killed=$((killed + 1))
        else
            echo "   ⚠️  跳过 PID $pid (不是本项目进程): $cmdline"
            kept=$((kept + 1))
        fi
    done

    # 如果有非本项目进程占用 → 报错退出
    if [ $kept -gt 0 ]; then
        echo ""
        echo "❌ 端口 $port 被 $kept 个非项目进程占用，无法自动清理"
        echo "   请手动: lsof -i :$port 查 PID，确认是否可以 kill"
        return 1
    fi

    if [ $killed -gt 0 ]; then
        echo "   ✓ 清理了 $killed 个进程"
        sleep 1
    fi
    return 0
}

# ============ 启动后端 ============
start_backend() {
    echo "🚀 启动后端 (port $BACKEND_PORT)..."
    cd "$PROJECT_ROOT"
    nohup "$UVICORN" realtime_novel.api.app:app \
        --host "$HOST" \
        --port "$BACKEND_PORT" \
        --log-level info \
        > "$LOG_DIR/backend.log" 2>&1 &
    echo $! > "$PID_DIR/backend.pid"

    # 等后端就绪
    for i in {1..15}; do
        if curl -s "http://$HOST:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
            echo "   ✓ 后端就绪 (http://$HOST:$BACKEND_PORT)"
            return 0
        fi
        sleep 1
    done
    echo "   ❌ 后端启动超时，查看日志: $LOG_DIR/backend.log"
    return 1
}

# ============ 启动前端 ============
start_frontend() {
    echo "🚀 启动前端 (port $FRONTEND_PORT)..."
    cd "$PROJECT_ROOT/frontend"
    nohup npm run dev -- --port "$FRONTEND_PORT" > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$PID_DIR/frontend.pid"

    # 等前端就绪
    for i in {1..15}; do
        if curl -s "http://localhost:$FRONTEND_PORT/" > /dev/null 2>&1; then
            echo "   ✓ 前端就绪 (http://localhost:$FRONTEND_PORT)"
            return 0
        fi
        sleep 1
    done
    echo "   ❌ 前端启动超时，查看日志: $LOG_DIR/frontend.log"
    return 1
}

# ============ 入口 ============
main() {
    echo "============================================================"
    echo "  realtime-novel · 一键启动"
    echo "  前端: http://localhost:$FRONTEND_PORT"
    echo "  后端: http://$HOST:$BACKEND_PORT"
    echo "  API:  http://localhost:$FRONTEND_PORT/api/health (走代理)"
    echo "============================================================"
    echo ""

    check_env
    check_dependencies
    kill_port_if_used $BACKEND_PORT "后端" || exit 1
    kill_port_if_used $FRONTEND_PORT "前端" || exit 1

    start_backend
    start_frontend

    echo ""
    echo "✅ 启动完成"
    echo ""
    echo "  浏览器打开: http://localhost:$FRONTEND_PORT/"
    echo "  API 文档:   http://$HOST:$BACKEND_PORT/docs"
    echo "  停止:       scripts/stop.sh"
    echo "  日志:       tail -f $LOG_DIR/{backend,frontend}.log"
    echo ""
}

main "$@"
