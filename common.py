# -*- coding: utf-8 -*-
"""Shared utilities: timezone, logging, captcha solving, login retry, notifications."""

import asyncio
import base64
import logging
import os
import time
from datetime import timezone, timedelta
from typing import Optional, Callable, Awaitable, Tuple

# Use Beijing timezone
BEIJING_TZ = timezone(timedelta(hours=8))


def get_logger(name: str = __name__) -> logging.Logger:
    """Initialize and return a logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    return logging.getLogger(name)


async def solve_captcha(page, ocr, logger: logging.Logger, max_attempts: int = 3) -> str:
    """Generic captcha solver: screenshot -> OCR -> keep 4 digits."""
    try:
        await page.wait_for_selector("div.captcha-image img", timeout=15000)
    except Exception:
        logger.error("captcha image not found")
        return ""

    for attempt in range(max_attempts):
        captcha_img = await page.query_selector("div.captcha-image img")
        if not captcha_img:
            logger.error("captcha image element missing")
            return ""

        try:
            img_data = await captcha_img.screenshot(type="png")
        except Exception as e:
            logger.warning(f"screenshot captcha failed, fallback base64: {e}")
            src = await captcha_img.get_attribute("src")
            if not src or not src.startswith("data:image"):
                logger.error("captcha image format invalid")
                return ""
            base64_data = src.split(",")[1]
            img_data = base64.b64decode(base64_data)

        if ocr:
            raw_text = ocr.classification(img_data)
            captcha_text = "".join(ch for ch in raw_text if ch.isdigit())
            if len(captcha_text) == 4:
                logger.info(f"captcha result: {captcha_text}")
                return captcha_text

            logger.warning(
                f"captcha invalid. raw: {raw_text}, filtered: {captcha_text}, refreshing (attempt {attempt + 1})"
            )
            try:
                await captcha_img.click()
                await asyncio.sleep(0.6)
            except Exception as e:
                logger.warning(f"refresh captcha failed: {e}")
        else:
            logger.warning("OCR unavailable, cannot solve captcha automatically")
            return ""

    logger.error("captcha attempts exceeded")
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
    """Generic login with total timeout and retries."""
    start_ts = time.monotonic()
    attempt = 0

    try:
        await page.goto(login_url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
    except Exception as e:
        logger.error(f"open login page failed: {e}")
        return False

    while attempt < max_attempts and (time.monotonic() - start_ts) < total_timeout:
        attempt += 1
        logger.info(f"login attempt {attempt}/{max_attempts}")
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

            login_button = await page.query_selector('button:has-text("登录"), .login-btn, .submit-btn')
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
                logger.info(f"login success, current page: {page.url}")
                return True

            logger.warning("login may have failed, retrying...")
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"login flow error: {e}")
            await asyncio.sleep(2)

    logger.error("login timeout or retries exceeded")
    return False


async def send_wxpush(
    title: str,
    message: str,
    logger: logging.Logger,
    request_client,
    max_retries: int = 3,
    timeout: int = 10,
) -> None:
    """WXPush (Cloudflare Worker) notification. Skips if not configured."""
    base_url = (os.getenv("WXPUSH_URL") or "").rstrip("/")
    token = os.getenv("WXPUSH_TOKEN") or ""
    userid = os.getenv("WXPUSH_USERID") or ""

    if not base_url or not token:
        logger.info("WXPush not configured, skip")
        return

    url = f"{base_url}/wxsend"
    payload = {"title": title, "content": message}
    if userid:
        payload["userid"] = userid  # Override default recipients

    headers = {"Authorization": token, "Content-Type": "application/json"}

    for attempt in range(1, max_retries + 1):
        try:
            resp = request_client.post(url, json=payload, headers=headers, timeout=timeout)
            text = resp.text
            if resp.ok:
                logger.info(f"WXPush sent: {resp.status_code} {text}")
                return
            logger.warning(f"WXPush failed (attempt {attempt}): {resp.status_code} {text}")
        except Exception as e:
            logger.warning(f"WXPush error (attempt {attempt}): {e}")
        await asyncio.sleep(2 * attempt)

    logger.error("WXPush failed after retries")


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
    """WxPusher notification with retries. request_client must be requests-compatible."""
    if not app_token or not uid:
        logger.warning("WxPusher not configured, skip")
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
                logger.info("WxPusher sent")
                return
            logger.warning(f"WxPusher failed (attempt {attempt}): {result.get('msg')}")
        except Exception as e:
            logger.warning(f"WxPusher error (attempt {attempt}): {e}")
        await asyncio.sleep(2 * attempt)

    logger.error("WxPusher failed after retries")


async def run_with_retries(
    action_name: str,
    task_coro_factory: Callable[[], Awaitable[bool]],
    logger: logging.Logger,
    max_attempts: int = 3,
    delay_seconds: int = 60,
    backoff_factor: float = 1.0,
) -> Tuple[bool, int]:
    """Generic retry wrapper; returns success flag and attempts used."""
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        start_ts = time.monotonic()
        try:
            success = await task_coro_factory()
        except Exception as exc:
            logger.error(f"{action_name} attempt {attempt} raised: {exc}")
            success = False

        if success:
            elapsed = time.monotonic() - start_ts
            if attempt > 1:
                logger.info(f"{action_name} succeeded on attempt {attempt}, elapsed {elapsed:.1f}s")
            return True, attempt

        if attempt >= attempts:
            break

        wait_seconds = max(1, int(delay_seconds * (backoff_factor ** (attempt - 1))))
        logger.warning(f"{action_name} attempt {attempt}/{attempts} failed, retry in {wait_seconds}s")
        await asyncio.sleep(wait_seconds)

    logger.error(f"{action_name} failed after {attempts} attempts, stop retrying")
    return False, attempts
