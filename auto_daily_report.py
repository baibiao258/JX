"""
自动日报脚本
使用 Playwright 进行自动化日报提交
支持验证码识别和定时运行
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright, Page, Browser
import logging

BEIJING_TZ = timezone(timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

try:
    import ddddocr
    ocr = ddddocr.DdddOcr(show_ad=False)
    logger.info("ddddocr 库已加载，将使用自动验证码识别")
except ImportError:
    ocr = None
    logger.warning("ddddocr 库未安装")
except Exception as e:
    ocr = None
    logger.warning(f"ddddocr 初始化失败: {e}")


class AutoDailyReport:
    """自动日报类"""
    
    def __init__(self, username: str, password: str, headless: bool = True):
        self.username = username
        self.password = password
        self.headless = headless
        self.login_url = "https://qd.dxssxdk.com/lanhu_yonghudenglu"
        self.browser: Browser = None
        self.page: Page = None
        self.report_already_submitted = False
        
    async def solve_captcha(self) -> str:
        """识别验证码"""
        try:
            await self.page.wait_for_selector('div.captcha-image img', timeout=15000)
            captcha_img = await self.page.query_selector('div.captcha-image img')
            
            if not captcha_img:
                return ""
            
            src = await captcha_img.get_attribute('src')
            if not src or not src.startswith('data:image'):
                return ""
            
            import base64
            base64_data = src.split(',')[1]
            img_data = base64.b64decode(base64_data)
            
            if ocr:
                captcha_text = ocr.classification(img_data)
                logger.info(f"验证码识别结果: {captcha_text}")
                return captcha_text
            return ""
        except Exception as e:
            logger.error(f"验证码识别失败: {e}")
            return ""

    async def login_unlimited(self) -> bool:
        """登录系统 - 无限次重试直到成功"""
        logger.info(f"正在打开登录页面: {self.login_url}")
        
        try:
            await self.page.goto(self.login_url, wait_until='networkidle', timeout=60000)
            logger.info("登录页面加载完成")
            await asyncio.sleep(3)
            
            attempt = 0
            while True:
                attempt += 1
                logger.info(f"登录尝试 {attempt} - 无限次重试模式")
                
                try:
                    await self.page.wait_for_selector('input[type="text"][placeholder="请输入用户名"]', timeout=30000)
                    await self.page.fill('input[type="text"][placeholder="请输入用户名"]', self.username)
                    await self.page.fill('input[type="password"][placeholder="请输入密码"]', self.password)
                    
                    captcha_text = await self.solve_captcha()
                    if not captcha_text:
                        await self.page.reload(wait_until='networkidle', timeout=60000)
                        await asyncio.sleep(3)
                        continue
                    
                    await self.page.fill('input[type="text"][placeholder="请输入验证码"]', captcha_text)
                    
                    login_button = await self.page.query_selector('button:has-text("登录"), .login-btn, .submit-btn')
                    if login_button:
                        await login_button.click()
                    else:
                        await self.page.press('input[type="text"][placeholder="请输入验证码"]', 'Enter')
                    
                    await asyncio.sleep(3)
                    
                    try:
                        know_button = await self.page.wait_for_selector(
                            'button.van-button.van-button--default.van-button--large.van-dialog__confirm:has-text("我知道了")',
                            timeout=5000
                        )
                        if know_button:
                            await know_button.click()
                            await asyncio.sleep(1)
                    except:
                        pass
                    
                    if self.page.url != self.login_url:
                        logger.info(f"登录成功！当前页面: {self.page.url}")
                        return True
                    else:
                        logger.warning("登录可能失败，准备重试...")
                        await asyncio.sleep(2)
                        
                except Exception as e:
                    logger.error(f"登录过程出错: {e}")
                    await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return False
    
    async def check_today_report_submitted(self) -> bool:
        """检查今天的日报是否已提交"""
        try:
            logger.info("检查今天的日报是否已提交...")
            
            recent_tab = await self.page.wait_for_selector('div.tab-item:has-text("最近记录")', timeout=20000)
            if recent_tab:
                await recent_tab.click()
                await asyncio.sleep(2)
            
            try:
                refresh_button = await self.page.wait_for_selector('button.refresh-btn', timeout=10000)
                if refresh_button:
                    await refresh_button.click()
                    await asyncio.sleep(2)
            except:
                pass
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            try:
                report_date_element = await self.page.wait_for_selector('span.report-date', timeout=10000)
                if report_date_element:
                    report_date = await report_date_element.inner_text()
                    if report_date == today:
                        logger.info("✅ 日报已完成")
                        return True
            except:
                pass
            
            logger.info("❌ 日报未完成")
            return False
                
        except Exception as e:
            logger.error(f"检查日报状态时出错: {e}")
            return False

    async def click_ai_generate_with_retry(self, max_retries: int = 10) -> bool:
        """点击AI生成报告按钮，失败时自动重试"""
        for attempt in range(1, max_retries + 1):
            logger.info(f"AI生成报告尝试 {attempt}/{max_retries}")
            
            try:
                ai_button = await self.page.wait_for_selector('button.ai-generate-btn', timeout=15000)
                if ai_button:
                    await ai_button.click()
                    logger.info("✓ 已点击'AI生成报告'按钮")
                else:
                    continue
                
                for i in range(60):
                    await asyncio.sleep(1)
                    
                    try:
                        complete_toast = await self.page.query_selector('div.van-toast__text:has-text("AI生成完成")')
                        if complete_toast and await complete_toast.is_visible():
                            logger.info("✅ AI生成完成")
                            await asyncio.sleep(1)
                            return True
                    except:
                        pass
                    
                    try:
                        fail_toast = await self.page.query_selector('div.van-toast__text:has-text("AI生成失败")')
                        if fail_toast and await fail_toast.is_visible():
                            logger.warning("⚠️ AI生成失败，准备重试...")
                            await asyncio.sleep(2)
                            break
                    except:
                        pass
                else:
                    try:
                        textarea = await self.page.query_selector('textarea.content-textarea')
                        if textarea:
                            content = await textarea.input_value()
                            if content and len(content) > 10:
                                logger.info("✅ AI生成完成（通过检查内容确认）")
                                return True
                    except:
                        pass
                    
            except Exception as e:
                logger.error(f"AI生成报告出错: {e}")
                await asyncio.sleep(2)
        
        return False

    async def submit_daily_report(self) -> bool:
        """提交日报"""
        try:
            logger.info("开始提交日报...")
            await asyncio.sleep(3)
            
            # 第一步：点击"账号列表"导航
            try:
                account_nav = await self.page.wait_for_selector('span.nav-text:has-text("账号列表")', timeout=20000)
                if account_nav:
                    await account_nav.click()
                    logger.info("✓ 已点击'账号列表'导航")
                    await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"点击账号列表失败: {e}")
            
            # 第二步：点击"展开"按钮
            try:
                expand_button = await self.page.wait_for_selector('div.expand-icon', timeout=10000)
                if expand_button:
                    await expand_button.click()
                    logger.info("✓ 已点击'展开'按钮")
                    await asyncio.sleep(2)
            except:
                pass
            
            # 第三步：点击"生成报告"按钮
            try:
                report_button = None
                for selector in ['button.action-btn:has-text("生成报告")', 'button:has-text("生成报告")']:
                    try:
                        report_button = await self.page.wait_for_selector(selector, timeout=8000)
                        if report_button:
                            break
                    except:
                        continue
                
                if report_button:
                    await report_button.click()
                    logger.info("✓ 已点击'生成报告'按钮")
                    await asyncio.sleep(3)
                else:
                    logger.error("未找到'生成报告'按钮")
                    return False
            except Exception as e:
                logger.error(f"查找'生成报告'按钮时出错: {e}")
                return False
            
            # 第四步：检查今天的日报是否已提交
            if await self.check_today_report_submitted():
                self.report_already_submitted = True
                return True
            
            # 第五步：点击"生成报告"标签
            try:
                generate_tab = await self.page.wait_for_selector('div.tab-item:has-text("生成报告")', timeout=10000)
                if generate_tab:
                    await generate_tab.click()
                    await asyncio.sleep(2)
            except:
                pass
            
            # 第六步：点击"AI生成报告"按钮
            if not await self.click_ai_generate_with_retry():
                logger.error("AI生成报告失败")
                return False
            
            # 第七步：点击"提交报告"按钮
            try:
                submit_button = await self.page.wait_for_selector('button.submit-btn', timeout=20000)
                if submit_button:
                    await submit_button.click()
                    logger.info("✓ 已点击'提交报告'按钮")
                    
                    for i in range(30):
                        await asyncio.sleep(1)
                        try:
                            success_toast = await self.page.query_selector('div.van-toast__text:has-text("报告提交成功")')
                            if success_toast and await success_toast.is_visible():
                                logger.info("✅ 报告提交成功！")
                                return True
                        except:
                            pass
                    
                    return True
            except Exception as e:
                logger.error(f"点击提交报告按钮失败: {e}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 提交日报失败: {e}")
            return False

    async def run(self) -> bool:
        """运行自动日报流程"""
        playwright = None
        try:
            playwright = await async_playwright().start()
            
            self.browser = await playwright.chromium.launch(
                headless=self.headless,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            self.page = await context.new_page()
            logger.info("浏览器启动成功")
            
            if not await self.login_unlimited():
                logger.error("登录失败，终止日报流程")
                return False
            
            if not await self.submit_daily_report():
                logger.error("日报提交失败")
                return False
            
            logger.info("✅ 自动日报完成！")
            return True
            
        except Exception as e:
            logger.error(f"自动日报流程出错: {e}")
            return False
            
        finally:
            try:
                if self.page:
                    await asyncio.sleep(2)
                if self.browser:
                    await self.browser.close()
                if playwright:
                    await playwright.stop()
            except:
                pass


import requests

def send_notification(app_token: str, uid: str, title: str, message: str):
    """发送 WxPusher 通知"""
    if not app_token or not uid:
        return
        
    url = "https://wxpusher.zjiecode.com/api/send/message"
    
    try:
        data = {
            "appToken": app_token,
            "content": f"# {title}\n\n{message}",
            "summary": title,
            "contentType": 3,
            "uids": [uid],
            "verifyPay": False
        }
        
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        
        if result.get('code') == 1000:
            logger.info("✅ WxPusher 通知发送成功")
        else:
            logger.warning(f"⚠️ WxPusher 通知发送失败: {result.get('msg')}")
    except Exception as e:
        logger.warning(f"⚠️ 发送通知时出错: {e}")


async def main():
    """主函数"""
    username = os.getenv('CHECKIN_USERNAME', '')
    password = os.getenv('CHECKIN_PASSWORD', '')
    wxpusher_app_token = os.getenv('WXPUSHER_APP_TOKEN', '')
    wxpusher_uid = os.getenv('WXPUSHER_UID', '')
    
    if not username or not password:
        if len(sys.argv) >= 3:
            username = sys.argv[1]
            password = sys.argv[2]
        else:
            logger.error("请设置环境变量 CHECKIN_USERNAME 和 CHECKIN_PASSWORD")
            return
    
    now_beijing = datetime.now(BEIJING_TZ)
    
    logger.info(f"========== 自动日报开始 ==========")
    logger.info(f"时间: {now_beijing.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    logger.info(f"用户: {username}")
    logger.info(f"环境: Docker 容器")
    
    report = AutoDailyReport(username=username, password=password, headless=True)
    success = await report.run()
    
    finish_time = datetime.now(BEIJING_TZ)
    date_str = finish_time.strftime('%Y年%m月%d日')
    time_str = finish_time.strftime('%H:%M:%S')
    
    if success:
        if report.report_already_submitted:
            title = "日报已完成 ✅"
            message = f"""**今日日报已提交！**

📅 **日期**: {date_str}
⏰ **时间**: {time_str} (北京时间)
👤 **用户**: {username}
✨ **状态**: 日报已完成"""
        else:
            title = "日报完成 ✅"
            message = f"""**日报提交完成！**

📅 **日期**: {date_str}
⏰ **时间**: {time_str} (北京时间)
👤 **用户**: {username}
✨ **状态**: 日报已成功提交"""
        
        logger.info(f"========== 日报完成！ ==========")
        send_notification(wxpusher_app_token, wxpusher_uid, title, message)
    else:
        title = "日报未完成 ❌"
        message = f"""**日报提交失败！**

📅 **日期**: {date_str}
⏰ **时间**: {time_str} (北京时间)
👤 **用户**: {username}
❌ **状态**: 日报提交失败"""
        
        logger.error(f"========== 日报未完成！ ==========")
        send_notification(wxpusher_app_token, wxpusher_uid, title, message)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
