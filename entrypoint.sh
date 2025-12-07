#!/bin/bash
set -e

echo "========== 打卡脚本容器启动 =========="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "用户: $CHECKIN_USERNAME"

# 运行打卡脚本
python auto_checkin.py

# 脚本执行完后保持容器运行
echo "========== 打卡脚本执行完成 =========="
echo "容器将保持运行状态..."
tail -f /dev/null
