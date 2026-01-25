#!/usr/bin/env python3
"""
WEEX 浏览器端网格交易完整测试

本脚本使用 Selenium WebDriver 控制 Chrome 浏览器，直接在 WEEX 网页端执行网格交易。
通过 JavaScript 注入与 Tampermonkey 脚本交互，实现完整的下单、监控、成交流程。

测试流程：
1. 启动 Chrome 浏览器并导航到 WEEX 交易页面
2. 注入 Tampermonkey 脚本到页面
3. 调用脚本函数执行网格交易
4. 监控订单状态和成交情况
5. 收集测试数据并生成报告
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WeexBrowserGridTester:
    """WEEX 浏览器端网格交易测试器"""

    def __init__(self, headless: bool = False):
        """
        初始化测试器
        
        Args:
            headless: 是否以无头模式运行
        """
        self.driver = None
        self.headless = headless
        self.test_results = {
            "start_time": None,
            "end_time": None,
            "total_duration": 0,
            "orders_placed": 0,
            "orders_failed": 0,
            "buy_orders": [],
            "sell_orders": [],
            "order_book_snapshot": None,
            "current_price": None,
            "account_balance": None,
            "errors": []
        }

    def setup_driver(self) -> bool:
        """
        配置并启动 Chrome WebDriver
        
        Returns:
            bool: 是否成功启动
        """
        logger.info("=" * 60)
        logger.info("正在启动 Chrome WebDriver...")
        logger.info("=" * 60)
        
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("✓ WebDriver 启动成功")
            return True
        except WebDriverException as e:
            logger.error(f"✗ WebDriver 启动失败: {e}")
            self.test_results["errors"].append(f"WebDriver 启动失败: {e}")
            return False

    def inject_tampermonkey_script(self) -> bool:
        """
        将 Tampermonkey 脚本注入到页面
        
        Returns:
            bool: 是否成功注入
        """
        logger.info("正在注入 Tampermonkey 脚本...")
        
        try:
            script_path = Path("/home/ubuntu/weex_grid_bot.js")
            if not script_path.exists():
                logger.error(f"✗ 脚本文件不存在: {script_path}")
                self.test_results["errors"].append(f"脚本文件不存在: {script_path}")
                return False
            
            with open(script_path, 'r', encoding='utf-8') as f:
                script_content = f.read()
            
            # 移除 UserScript 头部和尾部
            if script_content.startswith("// ==UserScript=="):
                lines = script_content.split('\n')
                start_idx = next((i for i, line in enumerate(lines) if line == "// ==/UserScript=="), 0) + 1
                script_content = '\n'.join(lines[start_idx:])
            
            self.driver.execute_script(script_content)
            logger.info("✓ Tampermonkey 脚本注入成功")
            return True
        except Exception as e:
            logger.error(f"✗ 脚本注入失败: {e}")
            self.test_results["errors"].append(f"脚本注入失败: {e}")
            return False

    def get_current_price(self) -> float:
        """
        获取当前 BTC 价格
        
        Returns:
            float: 当前价格
        """
        try:
            price_element = self.driver.find_element(By.XPATH, "//span[contains(text(), 'USDT')]")
            price_text = price_element.text.replace(',', '')
            price = float(price_text.split()[0])
            self.test_results["current_price"] = price
            logger.info(f"当前 BTC 价格: {price} USDT")
            return price
        except Exception as e:
            logger.warning(f"获取价格失败: {e}")
            return 0

    def get_account_balance(self) -> Dict[str, Any]:
        """
        获取账户余额信息
        
        Returns:
            Dict: 账户余额信息
        """
        try:
            balance_script = """
            return {
                available: document.querySelector('[class*="available"]')?.textContent || 'N/A',
                equity: document.querySelector('[class*="equity"]')?.textContent || 'N/A',
                unrealized_pnl: document.querySelector('[class*="unrealized"]')?.textContent || 'N/A'
            };
            """
            balance = self.driver.execute_script(balance_script)
            self.test_results["account_balance"] = balance
            logger.info(f"账户信息: {balance}")
            return balance
        except Exception as e:
            logger.warning(f"获取账户信息失败: {e}")
            return {}

    def get_order_book_snapshot(self) -> Dict[str, Any]:
        """
        获取订单簿快照
        
        Returns:
            Dict: 订单簿数据
        """
        try:
            orderbook_script = """
            const asks = [];
            const bids = [];
            
            // 获取卖单（Ask）
            document.querySelectorAll('[id^="ask-contract"]').forEach(el => {
                const price = el.textContent.replace(/,/g, '');
                if (price) asks.push(parseFloat(price));
            });
            
            // 获取买单（Bid）
            document.querySelectorAll('[id^="bid-contract"]').forEach(el => {
                const price = el.textContent.replace(/,/g, '');
                if (price) bids.push(parseFloat(price));
            });
            
            return {
                asks: asks.slice(0, 5),
                bids: bids.slice(0, 5),
                spread: asks.length > 0 && bids.length > 0 ? (asks[0] - bids[0]).toFixed(2) : 'N/A'
            };
            """
            orderbook = self.driver.execute_script(orderbook_script)
            self.test_results["order_book_snapshot"] = orderbook
            logger.info(f"订单簿快照: {orderbook}")
            return orderbook
        except Exception as e:
            logger.warning(f"获取订单簿失败: {e}")
            return {}

    def execute_grid_trading(self) -> bool:
        """
        执行网格交易
        
        Returns:
            bool: 是否成功执行
        """
        logger.info("=" * 60)
        logger.info("开始执行网格交易...")
        logger.info("=" * 60)
        
        self.test_results["start_time"] = datetime.now().isoformat()
        
        try:
            # 调用 Tampermonkey 脚本中的 startGridTrading 函数
            result = self.driver.execute_async_script("""
                const callback = arguments[arguments.length - 1];
                if (window.startGridTrading) {
                    window.startGridTrading()
                        .then(stats => callback({success: true, stats: stats}))
                        .catch(error => callback({success: false, error: error.message}));
                } else {
                    callback({success: false, error: 'startGridTrading function not found'});
                }
            """, timeout=120)
            
            if result.get("success"):
                logger.info("✓ 网格交易执行成功")
                stats = result.get("stats", {})
                self.test_results["orders_placed"] = stats.get("placed", 0)
                self.test_results["orders_failed"] = stats.get("failed", 0)
                self.test_results["buy_orders"] = stats.get("buy_orders", [])
                self.test_results["sell_orders"] = stats.get("sell_orders", [])
                logger.info(f"订单统计: {stats}")
                return True
            else:
                error_msg = result.get("error", "未知错误")
                logger.error(f"✗ 网格交易执行失败: {error_msg}")
                self.test_results["errors"].append(f"网格交易执行失败: {error_msg}")
                return False
        except TimeoutException:
            logger.error("✗ 网格交易执行超时")
            self.test_results["errors"].append("网格交易执行超时")
            return False
        except Exception as e:
            logger.error(f"✗ 网格交易执行异常: {e}")
            self.test_results["errors"].append(f"网格交易执行异常: {e}")
            return False

    def monitor_orders(self, duration: int = 30) -> None:
        """
        监控订单状态
        
        Args:
            duration: 监控时长（秒）
        """
        logger.info("=" * 60)
        logger.info(f"监控订单状态（{duration}秒）...")
        logger.info("=" * 60)
        
        start_time = time.time()
        check_interval = 5
        
        while time.time() - start_time < duration:
            try:
                # 获取当前委托数量
                orders_script = """
                const orderText = document.querySelector('[class*="current"]')?.textContent || '';
                const match = orderText.match(/\\((\\d+)\\)/);
                return match ? parseInt(match[1]) : 0;
                """
                current_orders = self.driver.execute_script(orders_script)
                elapsed = int(time.time() - start_time)
                logger.info(f"[{elapsed}s] 当前委托数: {current_orders}")
                
                time.sleep(check_interval)
            except Exception as e:
                logger.warning(f"监控失败: {e}")
                time.sleep(check_interval)

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        获取开放订单列表
        
        Returns:
            List: 开放订单列表
        """
        logger.info("获取开放订单列表...")
        
        try:
            orders_script = """
            const orders = [];
            const rows = document.querySelectorAll('table tbody tr');
            
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 7) {
                    orders.push({
                        time: cells[0]?.textContent || '',
                        symbol: cells[1]?.textContent || '',
                        direction: cells[2]?.textContent || '',
                        quantity: cells[5]?.textContent || '',
                        price: cells[7]?.textContent || '',
                        status: cells[9]?.textContent || ''
                    });
                }
            });
            
            return orders;
            """
            orders = self.driver.execute_script(orders_script)
            logger.info(f"获取到 {len(orders)} 个开放订单")
            return orders
        except Exception as e:
            logger.warning(f"获取开放订单失败: {e}")
            return []

    async def run_test(self) -> bool:
        """
        运行完整的测试流程
        
        Returns:
            bool: 测试是否成功
        """
        try:
            # 1. 启动浏览器
            if not self.setup_driver():
                return False
            
            # 2. 导航到 WEEX 交易页面
            logger.info("导航到 WEEX 交易页面...")
            weex_url = "https://www.weex.com/zh-CN/futures/BTC-USDT"
            self.driver.get(weex_url)
            
            # 等待页面加载
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '买入开多')]"))
                )
                logger.info("✓ 页面加载完成")
            except TimeoutException:
                logger.warning("⚠ 页面加载超时，继续执行...")
            
            await asyncio.sleep(3)
            
            # 3. 获取初始状态
            self.get_current_price()
            self.get_account_balance()
            self.get_order_book_snapshot()
            
            # 4. 注入脚本
            if not self.inject_tampermonkey_script():
                return False
            
            await asyncio.sleep(2)
            
            # 5. 执行网格交易
            if not self.execute_grid_trading():
                return False
            
            # 6. 监控订单
            self.monitor_orders(duration=30)
            
            # 7. 获取最终状态
            self.get_open_orders()
            self.get_current_price()
            
            self.test_results["end_time"] = datetime.now().isoformat()
            
            logger.info("=" * 60)
            logger.info("✅ 测试完成！")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"测试异常: {e}", exc_info=True)
            self.test_results["errors"].append(f"测试异常: {e}")
            return False
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("WebDriver 已关闭")

    def save_results(self, output_path: str = "/home/ubuntu/weex_test_results.json") -> None:
        """
        保存测试结果到文件
        
        Args:
            output_path: 输出文件路径
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.test_results, f, indent=2, ensure_ascii=False)
            logger.info(f"✓ 测试结果已保存到: {output_path}")
        except Exception as e:
            logger.error(f"保存测试结果失败: {e}")


async def main():
    """主函数"""
    tester = WeexBrowserGridTester(headless=False)
    success = await tester.run_test()
    tester.save_results()
    
    if success:
        logger.info("\n" + "=" * 60)
        logger.info("测试总结")
        logger.info("=" * 60)
        logger.info(f"订单已下: {tester.test_results['orders_placed']}")
        logger.info(f"订单失败: {tester.test_results['orders_failed']}")
        logger.info(f"买入订单: {len(tester.test_results['buy_orders'])}")
        logger.info(f"卖出订单: {len(tester.test_results['sell_orders'])}")
        if tester.test_results["errors"]:
            logger.info(f"错误数: {len(tester.test_results['errors'])}")
            for error in tester.test_results["errors"]:
                logger.info(f"  - {error}")


if __name__ == "__main__":
    asyncio.run(main())
