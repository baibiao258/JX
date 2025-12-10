# -*- coding: utf-8 -*-
"""
自动日报脚本
使用 Playwright 自动化提交日报，支持验证码识别、重试与通知。
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser
import logging
import requests
from typing import Optional

from common import BEIJING_TZ, get_logger, login_with_retry, run_with_retries, send_wxpusher

logger = get_logger(__name__)

try:
    import ddddocr

    ocr = ddddocr.DdddOcr(show_ad=False)
    logger.info("ddddocr 库已加载，将使用自动验证码识别")
except ImportError:
    ocr = None
    logger.warning("ddddocr 库未安装，将无法自动识别验证码")
except Exception as e:
    ocr = None
    logger.warning(f"ddddocr 初始化失败: {e}")


def _get_int_env(var_name: str, default: int) -> int:
    """读取整数环境变量，非法时使用默认值。"""
    try:
        return int(os.getenv(var_name, str(default)))
    except Exception:
        logger.warning(f"环境变量 {var_name} 非法，使用默认值 {default}")
        return default


def _get_float_env(var_name: str, default: float) -> float:
    """读取浮点环境变量，非法时使用默认值。"""
    try:
        return float(os.getenv(var_name, str(default)))
    except Exception:
        logger.warning(f"环境变量 {var_name} 非法，使用默认值 {default}")
        return default


class AutoDailyReport:
    """自动日报类"""

    def __init__(self, username: str, password: str, headless: bool = True):
        self.username = username
        self.password = password
        self.headless = headless
        self.login_url = "https://qd.dxssxdk.com/lanhu_yonghudenglu"
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.report_already_submitted = False

    async def login_unlimited(self) -> bool:
        """登录系统：带总超时与重试。"""
        logger.info(f"正在打开登录页面: {self.login_url}")
        return await login_with_retry(
            self.page,
            self.username,
            self.password,
            self.login_url,
            ocr,
            logger,
            max_attempts=10,
            total_timeout=240,
        )

    async def check_today_report_submitted(self) -> bool:
        """检查今天的日报是否已提交。"""
        try:
            logger.info("检查今天的日报是否已提交...")

            try:
                recent_tab = await self.page.wait_for_selector(
                    'div.tab-item:has-text("最近记录")', timeout=15000
                )
                if recent_tab:
                    await recent_tab.click()
                    await asyncio.sleep(1.5)
            except Exception:
                pass

            try:
                refresh_button = await self.page.wait_for_selector(
                    "button.refresh-btn", timeout=8000
                )
                if refresh_button:
                    await refresh_button.click()
                    await asyncio.sleep(1.5)
            except Exception:
                pass

            today = datetime.now().strftime("%Y-%m-%d")

            try:
                report_date_element = await self.page.wait_for_selector(
                    "span.report-date", timeout=8000
                )
                if report_date_element:
                    report_date = await report_date_element.inner_text()
                    if report_date == today:
                        logger.info("今日日报已完成")
                        return True
            except Exception:
                pass

            logger.info("今日日报未完成")
            return False

        except Exception as e:
            logger.error(f"检查日报状态时出错: {e}")
            return False

    async def click_ai_generate_with_retry(
        self, max_retries: int = 5, wait_per_attempt: int = 30, total_timeout: int = 180
    ) -> bool:
        """点击 AI 生成报告按钮，失败时自动重试，限制总时长。"""
        deadline = time.monotonic() + total_timeout
        for attempt in range(1, max_retries + 1):
            if time.monotonic() > deadline:
                logger.error("AI 生成超过总超时限制")
                return False

            logger.info(f"AI 生成报告尝试 {attempt}/{max_retries}")
            try:
                ai_button = await self.page.wait_for_selector(
                    "button.ai-generate-btn", timeout=15000
                )
                if ai_button:
                    await ai_button.click()
                    logger.info("已点击 AI 生成报告按钮")
                else:
                    continue

                attempt_deadline = time.monotonic() + wait_per_attempt
                while time.monotonic() < attempt_deadline:
                    await asyncio.sleep(1)

                    try:
                        complete_toast = await self.page.query_selector(
                            'div.van-toast__text:has-text("AI生成完成")'
                        )
                        if complete_toast and await complete_toast.is_visible():
                            logger.info("AI 生成完成")
                            await asyncio.sleep(1)
                            return True
                    except Exception:
                        pass

                    try:
                        fail_toast = await self.page.query_selector(
                            'div.van-toast__text:has-text("AI生成失败")'
                        )
                        if fail_toast and await fail_toast.is_visible():
                            logger.warning("AI 生成失败，准备重试...")
                            await asyncio.sleep(2)
                            break
                    except Exception:
                        pass

                # 如果没有明确成功，再检查内容是否生成
                try:
                    textarea = await self.page.query_selector("textarea.content-textarea")
                    if textarea:
                        content = await textarea.input_value()
                        if content and len(content) > 10:
                            logger.info("AI 生成完成（通过内容校验）")
                            return True
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"AI 生成报告出错: {e}")
                await asyncio.sleep(2)

        return False

    async def submit_daily_report(self) -> bool:
        """提交日报：确保成功 toast，否则视为失败。"""
        try:
            logger.info("开始提交日报...")
            await asyncio.sleep(1.5)

            # 第一步：点击"账号列表"导航
            try:
                account_nav = await self.page.wait_for_selector(
                    'span.nav-text:has-text("账号列表")', timeout=15000
                )
                if account_nav:
                    await account_nav.click()
                    logger.info("已点击账号列表导航")
                    await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"点击账号列表失败: {e}")

            # 第二步：点击"展开"按钮
            try:
                expand_button = await self.page.wait_for_selector(
                    "div.expand-icon", timeout=8000
                )
                if expand_button:
                    await expand_button.click()
                    logger.info("已点击展开按钮")
                    await asyncio.sleep(1)
            except Exception:
                pass

            # 第三步：点击"生成报告"按钮
            try:
                report_button = None
                for selector in ['button.action-btn:has-text("生成报告")', 'button:has-text("生成报告")']:
                    try:
                        report_button = await self.page.wait_for_selector(selector, timeout=8000)
                        if report_button:
                            break
                    except Exception:
                        continue

                if report_button:
                    await report_button.click()
                    logger.info("已点击生成报告按钮")
                    await asyncio.sleep(2)
                else:
                    logger.error("未找到生成报告按钮")
                    return False
            except Exception as e:
                logger.error(f"查找生成报告按钮时出错: {e}")
                return False

            # 第四步：检查今天的日报是否已提交
            if await self.check_today_report_submitted():
                self.report_already_submitted = True
                return True

            # 第五步：点击"生成报告"标签
            try:
                generate_tab = await self.page.wait_for_selector(
                    'div.tab-item:has-text("生成报告")', timeout=8000
                )
                if generate_tab:
                    await generate_tab.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            # 第六步：点击"AI生成报告"按钮
            if not await self.click_ai_generate_with_retry():
                logger.error("AI 生成报告失败")
                return False

            # 第七步：点击"提交报告"按钮
            try:
                submit_button = await self.page.wait_for_selector("button.submit-btn", timeout=15000)
                if submit_button:
                    await submit_button.click()
                    logger.info("已点击提交报告按钮")

                    for _ in range(30):
                        await asyncio.sleep(1)
                        try:
                            success_toast = await self.page.query_selector(
                                'div.van-toast__text:has-text("报告提交成功")'
                            )
                            if success_toast and await success_toast.is_visible():
                                logger.info("报告提交成功")
                                return True
                        except Exception:
                            pass

                    logger.error("未检测到提交成功提示，视为失败")
                    return False
            except Exception as e:
                logger.error(f"点击提交报告按钮失败: {e}")
                return False

        except Exception as e:
            logger.error(f"提交日报失败: {e}")
            return False

    async def run(self) -> bool:
        """运行自动日报流程。"""
        playwright = None
        try:
            playwright = await async_playwright().start()

            launch_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",  # 避免 /dev/shm 太小导致崩溃
            ]

            self.browser = await playwright.chromium.launch(headless=self.headless, args=launch_args)

            context = await self.browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )

            self.page = await context.new_page()
            logger.info("浏览器启动成功")

            if not await self.login_unlimited():
                logger.error("登录失败，终止日报流程")
                return False

            if not await self.submit_daily_report():
                logger.error("日报提交失败")
                return False

            logger.info("自动日报完成")
            return True

        except Exception as e:
            logger.error(f"自动日报流程出错: {e}")
            return False

        finally:
            try:
                if self.page:
                    await asyncio.sleep(1)
                if self.browser:
                    await self.browser.close()
                if playwright:
                    await playwright.stop()
            except Exception:
                pass


async def main():
    """主函数"""
    username = os.getenv("CHECKIN_USERNAME", "")
    password = os.getenv("CHECKIN_PASSWORD", "")
    wxpusher_app_token = os.getenv("WXPUSHER_APP_TOKEN", "")
    wxpusher_uid = os.getenv("WXPUSHER_UID", "")

    if not username or not password:
        if len(sys.argv) >= 3:
            username = sys.argv[1]
            password = sys.argv[2]
        else:
            logger.error("请设置环境变量 CHECKIN_USERNAME 和 CHECKIN_PASSWORD")
            return

    now_beijing = datetime.now(BEIJING_TZ)

    logger.info("========== 自动日报开始 ==========")
    logger.info(f"时间: {now_beijing.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    logger.info(f"用户: {username}")

    max_retry_attempts = _get_int_env("DAILY_REPORT_RETRY_ATTEMPTS", 3)
    retry_delay_seconds = _get_int_env("DAILY_REPORT_RETRY_DELAY", 90)
    retry_backoff = _get_float_env("DAILY_REPORT_RETRY_BACKOFF", 1.5)

    logger.info(
        f"日报重试配置: 最多 {max_retry_attempts} 次，初始间隔 {retry_delay_seconds}s，回退系数 {retry_backoff}"
    )

    report: Optional[AutoDailyReport] = None

    async def attempt_daily_report():
        nonlocal report
        report = AutoDailyReport(username=username, password=password, headless=True)
        return await report.run()

    success, used_attempts = await run_with_retries(
        action_name="日报提交",
        task_coro_factory=attempt_daily_report,
        logger=logger,
        max_attempts=max_retry_attempts,
        delay_seconds=retry_delay_seconds,
        backoff_factor=retry_backoff,
    )

    finish_time = datetime.now(BEIJING_TZ)
    date_str = finish_time.strftime("%Y年%m月%d日")
    time_str = finish_time.strftime("%H:%M:%S")

    if success:
        if report.report_already_submitted:
            title = "日报已完成"
            message = f"""今日日报已提交。

日期: {date_str}
时间: {time_str} (北京时间)
用户: {username}
重试: 第 {used_attempts} 次尝试成功（最多 {max_retry_attempts} 次）
状态: 日报已完成"""
        else:
            title = "日报完成"
            message = f"""日报提交完成。

日期: {date_str}
时间: {time_str} (北京时间)
用户: {username}
重试: 第 {used_attempts} 次尝试成功（最多 {max_retry_attempts} 次）
状态: 日报已成功提交"""

        logger.info("========== 日报完成 ==========")
        await send_wxpusher(wxpusher_app_token, wxpusher_uid, title, message, logger, requests)
    else:
        title = "日报未完成"
        message = f"""日报提交失败。

日期: {date_str}
时间: {time_str} (北京时间)
用户: {username}
重试: 已尝试 {max_retry_attempts} 次（全部失败）
状态: 日报提交失败"""

        logger.error("========== 日报未完成 ==========")
        await send_wxpusher(wxpusher_app_token, wxpusher_uid, title, message, logger, requests)


if __name__ == "__main__":
    asyncio.run(main())
