"""
定时任务调度器
支持每天指定时间自动运行打卡脚本
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
import logging
import schedule
import time

BEIJING_TZ = timezone(timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


async def run_checkin():
    """运行打卡脚本"""
    logger.info("=" * 50)
    logger.info("定时任务触发：开始执行打卡脚本")
    logger.info("=" * 50)
    
    # 动态导入打卡脚本的 main 函数
    from auto_checkin import main
    await main()


async def run_daily_report():
    """运行日报脚本"""
    logger.info("=" * 50)
    logger.info("定时任务触发：开始执行日报脚本")
    logger.info("=" * 50)
    
    # 动态导入日报脚本的 main 函数
    from auto_daily_report import main
    await main()


def schedule_jobs():
    """配置定时任务"""
    
    # 注意：schedule 库使用系统本地时间
    # 北京时间 07:00 = UTC 23:00 (前一天)
    # 北京时间 17:00 = UTC 09:00
    # 北京时间 17:40 = UTC 09:40
    
    # 上班打卡：北京时间 07:00 = UTC 23:00 (前一天)
    schedule.every().day.at("23:00").do(lambda: asyncio.run(run_checkin()))
    logger.info("✓ 已配置上班打卡：北京时间每天 07:00 (UTC 23:00)")
    
    # 下班打卡：北京时间 17:00 = UTC 09:00
    schedule.every().day.at("09:00").do(lambda: asyncio.run(run_checkin()))
    logger.info("✓ 已配置下班打卡：北京时间每天 17:00 (UTC 09:00)")
    
    # 日报提交：北京时间 17:40 = UTC 09:40
    schedule.every().day.at("09:40").do(lambda: asyncio.run(run_daily_report()))
    logger.info("✓ 已配置日报提交：北京时间每天 17:40 (UTC 09:40)")


async def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("打卡定时调度器启动")
    logger.info("=" * 50)
    
    # 配置定时任务
    schedule_jobs()
    
    # 获取北京时间
    now_beijing = datetime.now(BEIJING_TZ)
    logger.info(f"当前时间: {now_beijing.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    logger.info("定时调度器已启动，等待任务触发...")
    logger.info("=" * 50)
    
    # 持续运行调度器
    try:
        while True:
            schedule.run_pending()
            await asyncio.sleep(60)  # 每 60 秒检查一次是否有任务需要运行
    except KeyboardInterrupt:
        logger.info("定时调度器已停止")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
