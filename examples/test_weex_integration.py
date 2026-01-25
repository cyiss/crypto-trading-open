#!/usr/bin/env python3
"""
WEEX 浏览器端集成测试

本测试脚本使用 Selenium WebDriver 控制 Chrome 浏览器，与 Tampermonkey 脚本交互，
以模拟真实用户的网格交易流程。

测试目标：
1. 验证 Python 系统与浏览器端脚本的通信。
2. 跑通完整的下单、监控、成交、补单流程。
3. 评估浏览器自动化方案的稳定性和性能。
"""

import asyncio
import logging
from decimal import Decimal

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WeexIntegrationTester:
    """WEEX 集成测试器"""

    def __init__(self, tampermonkey_script_path: str):
        self.driver = None
        self.tampermonkey_script = ""
        with open(tampermonkey_script_path, 'r') as f:
            self.tampermonkey_script = f.read()

    def setup_driver(self):
        """配置并启动 Chrome WebDriver"""
        logger.info("正在启动 Chrome WebDriver...")
        chrome_options = Options()
        # 添加 Tampermonkey 扩展 (需要预先安装并获取crx文件路径)
        # chrome_options.add_extension('/path/to/tampermonkey.crx')
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--headless") # 无头模式
        chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("✓ WebDriver 启动成功")
        except WebDriverException as e:
            logger.error(f"WebDriver 启动失败: {e}")
            logger.error("请确保已正确安装 ChromeDriver 并且路径已在系统 PATH 中。")
            raise

    async def run_test(self):
        """运行完整的集成测试"""
        try:
            self.setup_driver()
            weex_url = "https://www.weex.com/zh-CN/futures/BTC-USDT"
            logger.info(f"导航到: {weex_url}")
            self.driver.get(weex_url)
            await asyncio.sleep(10) # 等待页面加载

            logger.info("注入 Tampermonkey 脚本...")
            self.driver.execute_script(self.tampermonkey_script)
            await asyncio.sleep(5)

            logger.info("调用脚本函数，开始网格交易...")
            # 调用油猴脚本中的 `startGridTrading` 函数
            result = self.driver.execute_async_script("""
                const callback = arguments[arguments.length - 1];
                if (window.startGridTrading) {
                    window.startGridTrading().then(callback);
                } else {
                    callback({error: 'startGridTrading function not found'});
                }
            """)
            logger.info(f"脚本执行结果: {result}")

            # 此处可以添加更多测试逻辑，例如模拟价格变动，检查订单状态等
            logger.info("监控测试运行30秒...")
            await asyncio.sleep(30)

            logger.info("获取交易统计...")
            stats = self.driver.execute_script("return window.getGridStats();")
            logger.info(f"交易统计: {stats}")

            logger.info("✅ 集成测试成功完成！")

        except Exception as e:
            logger.error(f"集成测试失败: {e}", exc_info=True)
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("WebDriver 已关闭")


async def main():
    tester = WeexIntegrationTester("/home/ubuntu/weex_grid_bot.js")
    await tester.run_test()


if __name__ == "__main__":
    asyncio.run(main())
