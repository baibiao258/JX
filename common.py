# -*- coding: utf-8 -*-
"""共享工具：时区、日志、验证码识别、统一登录重试。"""

import asyncio
import base64
import logging
import time
from datetime import timezone, timedelta
from typing import Optional, Callable, Awaitable, Tuple

# 统一使用北京时区
BEIJING_TZ = timezone(timedelta(hours=8))


def get_logger(name: str = __name__) -> logging.Logger:
    """初始化并返回同一日志格式的 logger。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    return logging.getLogger(name)


async def solve_captcha(page, ocr, logger: logging.Logger, max_attempts: int = 3) -> str:
    """通用验证码识别，优先截图，回退 base64，过滤出 4 位数字。"""
    try:
        await page.wait_for_selector("div.captcha-image img", timeout=15000)
    except Exception:
        logger.error("未找到验证码图片")
        return ""

    for attempt in range(max_attempts):
        captcha_img = await page.query_selector("div.captcha-image img")
        if not captcha_img:
            logger.error("验证码图片元素缺失")
            return ""

        try:
            img_data = await captcha_img.screenshot(type="png")
        except Exception as e:
            logger.warning(f"页面截图识别验证码失败，使用 base64 数据替代: {e}")
            src = await captcha_img.get_attribute("src")
            if not src or not src.startswith("data:image"):
                logger.error("验证码图片格式不正确")
                return ""
            base64_data = src.split(",")[1]
            img_data = base64.b64decode(base64_data)

        if ocr:
            raw_text = ocr.classification(img_data)
            captcha_text = "".join(ch for ch in raw_text if ch.isdigit())
            if len(captcha_text) == 4:
                logger.info(f"验证码识别结果 {captcha_text}")
                return captcha_text

            logger.warning(
                f"验证码识别结果无效，原始: {raw_text}，过滤后: {captcha_text}，尝试刷新验证码 (第{attempt + 1}次)"
            )
            try:
                await captcha_img.click()
                await asyncio.sleep(0.6)
            except Exception as e:
                logger.warning(f"刷新验证码失败: {e}")
        else:
            logger.warning("OCR 不可用，无法自动识别验证码")
            return ""

    logger.error("多次刷新后仍未获得有效验证码")
    return ""


async def login_with_retry(
    page,
    username: str,
    password: str,
    login_url: str,
    ocr,
    logger: logging.Logger,
    max_attempts: int = 10,
    total_timeout: int = 300,
) -> bool:
    """通用登录：带总超时与重试，失败时刷新页面。"""
    start_ts = time.monotonic()
    attempt = 0

    try:
        await page.goto(login_url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
    except Exception as e:
        logger.error(f"打开登录页失败: {e}")
        return False

    while attempt < max_attempts and (time.monotonic() - start_ts) < total_timeout:
        attempt += 1
        logger.info(f"登录尝试 {attempt}/{max_attempts}")
        try:
            await page.wait_for_selector('input[type="text"][placeholder="请输入用户名"]', timeout=30000)
            await page.fill('input[type="text"][placeholder="请输入用户名"]', username)
            await page.fill('input[type="password"][placeholder="请输入密码"]', password)

            captcha_text = await solve_captcha(page, ocr, logger)
            if not captcha_text:
                await page.reload(wait_until="networkidle", timeout=60000)
                await asyncio.sleep(2)
                continue

            await page.fill('input[type="text"][placeholder="请输入验证码"]', captcha_text)

            login_button = await page.query_selector('button:has-text("登录"), button:has-text("登录"), .login-btn, .submit-btn')
            if login_button:
                await login_button.click()
            else:
                await page.press('input[type="text"][placeholder="请输入验证码"]', "Enter")

            await asyncio.sleep(3)

            try:
                know_button = await page.wait_for_selector(
                    'button.van-button.van-button--default.van-button--large.van-dialog__confirm:has-text("我知道了")',
                    timeout=5000,
                )
                if know_button:
                    await know_button.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            if page.url != login_url:
                logger.info(f"登录成功，当前页: {page.url}")
                return True

            logger.warning("登录可能失败，准备重试...")
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"登录流程出错: {e}")
            await asyncio.sleep(2)

    logger.error("登录超时或超过最大重试次数")
    return False


async def send_wxpusher(
    app_token: str,
    uid: str,
    title: str,
    message: str,
    logger: logging.Logger,
    request_client,
    max_retries: int = 3,
    timeout: int = 10,
) -> None:
    """WxPusher 通知带重试。request_client 需兼容 requests 接口。"""
    if not app_token or not uid:
        logger.warning("未配置 WxPusher，跳过通知")
        return

    url = "https://wxpusher.zjiecode.com/api/send/message"
    data = {
        "appToken": app_token,
        "content": f"# {title}\n\n{message}",
        "summary": title,
        "contentType": 3,
        "uids": [uid],
        "verifyPay": False,
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = request_client.post(url, json=data, timeout=timeout)
            result = resp.json()
            if result.get("code") == 1000:
                logger.info("WxPusher 通知发送成功")
                return
            logger.warning(f"WxPusher 通知失败（第{attempt}次）: {result.get('msg')}")
        except Exception as e:
            logger.warning(f"发送通知出错（第{attempt}次）: {e}")
        await asyncio.sleep(2 * attempt)

    logger.error("WxPusher 通知多次重试后仍失败")


async def run_with_retries(
    action_name: str,
    task_coro_factory: Callable[[], Awaitable[bool]],
    logger: logging.Logger,
    max_attempts: int = 3,
    delay_seconds: int = 60,
    backoff_factor: float = 1.0,
) -> Tuple[bool, int]:
    """带自动重试的通用任务实现，返回成功与实际尝试次数。"""
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        start_ts = time.monotonic()
        try:
            success = await task_coro_factory()
        except Exception as exc:
            logger.error(f"{action_name} 第 {attempt} 次尝试出错: {exc}")
            success = False

        if success:
            elapsed = time.monotonic() - start_ts
            if attempt > 1:
                logger.info(f"{action_name} 在第 {attempt} 次尝试成功，耗时 {elapsed:.1f} 秒")
            return True, attempt

        if attempt >= attempts:
            break

        wait_seconds = max(1, int(delay_seconds * (backoff_factor ** (attempt - 1))))
        logger.warning(f"{action_name} 第 {attempt}/{attempts} 次失败，{wait_seconds} 秒后重试")
        await asyncio.sleep(wait_seconds)

    logger.error(f"{action_name} 连续 {attempts} 次失败，停止重试")
    return False, attempts

