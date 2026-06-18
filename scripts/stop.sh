#!/bin/bash
# stop.sh — 停止 start.sh 启动的 前后端进程

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="$PROJECT_ROOT/tmp/pids"

stop_one() {
    local name=$1
    local pidfile="$PID_DIR/$name.pid"
    if [ -f "$pidfile" ]; then
        local pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            echo "🛑 停止 $name (PID $pid)..."
            kill "$pid"
            # 等进程退出（最多 5s）
            for i in {1..5}; do
                if ! kill -0 "$pid" 2>/dev/null; then
                    break
                fi
                sleep 1
            done
            # 还活着就 kill -9
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
            echo "   ✓ $name 已停止"
        else
            echo "   ⚠️  $name PID $pid 已不存在"
        fi
        rm -f "$pidfile"
    else
        echo "   ⚠️  $name pidfile 不存在，跳过"
    fi
}

echo "停止前后端..."
stop_one backend
stop_one frontend
echo "✅ 完成"
