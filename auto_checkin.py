# -*- coding: utf-8 -*-
"""
自动打卡脚本 - 支持登录重试、验证码识别与通知。
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

from common import BEIJING_TZ, get_logger, login_with_retry, send_wxpusher

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


class AutoCheckin:
    """自动打卡类"""

    def __init__(self, username: str, password: str, headless: bool = True):
        self.username = username
        self.password = password
        self.headless = headless
        self.login_url = "https://qd.dxssxdk.com/lanhu_yonghudenglu"
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

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

    async def do_checkin(self) -> bool:
        """执行打卡操作。"""
        try:
            logger.info("开始执行打卡操作...")
            await asyncio.sleep(1)
            logger.info(f"当前页面 URL: {self.page.url}")

            # 第一步：点击"账号列表"导航
            try:
                account_nav = await self.page.wait_for_selector(
                    'span.nav-text:has-text("账号列表")', timeout=12000
                )
                if account_nav:
                    await account_nav.click()
                    logger.info("已点击账号列表导航")
                    await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"点击账号列表失败，尝试其他方式: {e}")
                try:
                    nav_items = await self.page.query_selector_all(".nav-item")
                    if len(nav_items) >= 2:
                        await nav_items[1].click()
                        logger.info("通过索引点击账号列表导航")
                        await asyncio.sleep(2)
                except Exception as e2:
                    logger.error(f"无法点击账号列表: {e2}")

            # 第二步：点击"展开"按钮
            try:
                expand_button = await self.page.wait_for_selector(
                    '.expand-icon, img[alt="展开"], .icon-image', timeout=8000
                )
                if expand_button:
                    await expand_button.click()
                    logger.info("已点击展开按钮")
                    await asyncio.sleep(1.5)
            except Exception:
                logger.info("未找到展开按钮，可能已展开")

            # 第三步：点击"提交打卡"按钮
            logger.info("查找并点击提交打卡按钮...")
            submit_button = None
            selectors = [
                'button.action-btn:has-text("提交打卡")',
                'button:has-text("提交打卡")',
                'button:has-text("打卡")',
                'button:has-text("提交")',
                ".action-btn",
                'button[class*="action"]',
                'button[class*="submit"]',
            ]

            for selector in selectors:
                try:
                    submit_button = await self.page.wait_for_selector(selector, timeout=3000)
                    if submit_button:
                        break
                except Exception:
                    continue

            if not submit_button:
                try:
                    all_buttons = await self.page.query_selector_all("button")
                    for btn in all_buttons:
                        try:
                            text = await btn.inner_text()
                            if "打卡" in text or "提交" in text:
                                submit_button = btn
                                break
                        except Exception:
                            continue
                except Exception as e:
                    logger.warning(f"遍历按钮时出错: {e}")

            if not submit_button:
                logger.error("未找到提交打卡按钮")
                return False

            await submit_button.click()
            logger.info("已点击提交打卡按钮")

            # 等待成功提示
            success_selectors = [
                'div.van-toast__text:has-text("成功")',
                'div.van-toast__text:has-text("已提交")',
                'div.van-toast__text:has-text("打卡成功")',
                ".success",
                ".toast",
            ]
            for _ in range(30):
                await asyncio.sleep(1)
                for selector in success_selectors:
                    try:
                        elem = await self.page.query_selector(selector)
                        if elem and await elem.is_visible():
                            text = await elem.inner_text()
                            logger.info(f"检测到成功提示: {text}")
                            return True
                    except Exception:
                        continue

            logger.error("未检测到打卡成功提示")
            return False

        except Exception as e:
            logger.error(f"打卡操作失败: {e}")
            return False

    async def run(self) -> bool:
        """运行自动打卡流程。"""
        playwright = None
        try:
            playwright = await async_playwright().start()

            self.browser = await playwright.chromium.launch(
                headless=self.headless, args=["--no-sandbox", "--disable-setuid-sandbox"]
            )

            context = await self.browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )

            self.page = await context.new_page()
            logger.info("浏览器启动成功")

            if not await self.login_unlimited():
                logger.error("登录失败，终止打卡流程")
                return False

            if not await self.do_checkin():
                logger.error("打卡失败")
                return False

            logger.info("自动打卡完成")
            return True

        except Exception as e:
            logger.error(f"自动打卡流程出错: {e}")
            return False

        finally:
            try:
                if self.page:
                    await asyncio.sleep(1)
                if self.browser:
                    await self.browser.close()
                    logger.info("浏览器已关闭")
                if playwright:
                    await playwright.stop()
            except Exception as e:
                logger.warning(f"关闭浏览器时出错: {e}")


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
            logger.error("请设置环境变量 CHECKIN_USERNAME 和 CHECKIN_PASSWORD，或通过命令行参数提供")
            logger.error("用法: python auto_checkin.py <用户名> <密码>")
            return

    now_beijing = datetime.now(BEIJING_TZ)
    current_hour = now_beijing.hour

    logger.info("========== 自动打卡开始（重试版） ==========")
    logger.info(f"时间: {now_beijing.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    logger.info(f"用户: {username}")
    if wxpusher_app_token and wxpusher_uid:
        logger.info("通知: 已配置 WxPusher")

    if 6 <= current_hour < 12:
        checkin_type = "上班"
        logger.info("当前时间在上班打卡时间段 (06:00-12:00)，执行上班打卡")
    elif 12 <= current_hour < 24:
        checkin_type = "下班"
        logger.info("当前时间在下班打卡时间段 (12:00-23:59)，执行下班打卡")
    else:
        logger.warning(f"当前时间 {current_hour}:00 不在打卡时间段内，跳过打卡")
        return

    checkin = AutoCheckin(username=username, password=password, headless=True)
    success = await checkin.run()

    finish_time = datetime.now(BEIJING_TZ)
    date_str = finish_time.strftime("%Y年%m月%d日")
    time_str = finish_time.strftime("%H:%M:%S")

    if success:
        title = f"{checkin_type}打卡成功"
        message = f"""{checkin_type}打卡成功。

日期: {date_str}
时间: {time_str} (北京时间)
用户: {username}
状态: 打卡成功"""

        logger.info(f"========== {checkin_type}打卡成功 ==========")
        await send_wxpusher(wxpusher_app_token, wxpusher_uid, title, message, logger, requests)
    else:
        title = f"{checkin_type}打卡失败"
        message = f"""{checkin_type}打卡失败，请人工检查。

日期: {date_str}
时间: {time_str} (北京时间)
用户: {username}
状态: 打卡失败"""

        logger.error(f"========== {checkin_type}打卡失败 ==========")
        await send_wxpusher(wxpusher_app_token, wxpusher_uid, title, message, logger, requests)


if __name__ == "__main__":
    asyncio.run(main())
