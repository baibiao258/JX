# -*- coding: utf-8 -*-
"""
定时任务调度器
支持每日固定时间自动运行打卡与日报脚本，带互斥避免并发重叠。
"""

import asyncio
import logging
from datetime import datetime
import schedule

from common import BEIJING_TZ, get_logger

logger = get_logger(__name__)
job_lock = asyncio.Lock()


async def run_guarded(name: str, coro_func):
    """带互斥锁的任务执行，避免并发重叠。"""
    if job_lock.locked():
        logger.warning(f"任务 {name} 正在执行，跳过本次触发")
        return

    async with job_lock:
        logger.info(f"任务 {name} 开始执行")
        try:
            await coro_func()
        except Exception as e:
            logger.error(f"任务 {name} 执行失败: {e}")
        finally:
            logger.info(f"任务 {name} 结束")


async def run_checkin():
    """运行打卡脚本"""
    logger.info("=" * 50)
    logger.info("定时任务触发：开始执行打卡脚本")
    logger.info("=" * 50)

    from auto_checkin import main

    await main()


async def run_daily_report():
    """运行日报脚本"""
    logger.info("=" * 50)
    logger.info("定时任务触发：开始执行日报脚本")
    logger.info("=" * 50)

    from auto_daily_report import main

    await main()


def schedule_jobs(loop: asyncio.AbstractEventLoop):
    """配置定时任务"""
    # 北京时间 07:00 = UTC 23:00 (前一天)
    schedule.every().day.at("23:00").do(
        lambda: loop.call_soon_threadsafe(asyncio.create_task, run_guarded("checkin_am", run_checkin))
    )
    logger.info("已配置上班打卡：北京时间每日 07:00 (UTC 23:00)")

    # 北京时间 17:00 = UTC 09:00
    schedule.every().day.at("09:00").do(
        lambda: loop.call_soon_threadsafe(asyncio.create_task, run_guarded("checkin_pm", run_checkin))
    )
    logger.info("已配置下班打卡：北京时间每日 17:00 (UTC 09:00)")

    # 北京时间 17:40 = UTC 09:40
    schedule.every().day.at("09:40").do(
        lambda: loop.call_soon_threadsafe(asyncio.create_task, run_guarded("daily_report", run_daily_report))
    )
    logger.info("已配置日报提交：北京时间每日 17:40 (UTC 09:40)")


async def main():
    """主函数：启动调度器"""
    logger.info("=" * 50)
    logger.info("打卡定时调度器启动")
    logger.info("=" * 50)

    loop = asyncio.get_running_loop()
    schedule_jobs(loop)

    now_beijing = datetime.now(BEIJING_TZ)
    logger.info(f"当前时间: {now_beijing.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    logger.info("定时调度器已启动，等待任务触发...")
    logger.info("=" * 50)

    try:
        while True:
            schedule.run_pending()
            await asyncio.sleep(30)  # 每 30 秒检查一次待执行任务
    except KeyboardInterrupt:
        logger.info("定时调度器已停止")


if __name__ == "__main__":
    asyncio.run(main())
