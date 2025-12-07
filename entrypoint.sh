#!/bin/bash
set -e

echo "========== 打卡脚本容器启动 =========="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "用户: $CHECKIN_USERNAME"
echo ""

# 运行定时调度器
python scheduler.py
