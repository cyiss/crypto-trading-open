#!/usr/bin/env python3
"""
WEEX Bot Controller - 通过浏览器工具与油猴脚本交互

本脚本定义了一个控制器类 `WeexBotBrowserController`，用于通过执行 JavaScript
与已注入到 WEEX 页面的油猴脚本 (`weex_grid_tampermonkey.js`) 进行通信。

它替代了原有的 WebSocket/HTTP 方案，提供了一个更直接、更稳定的控制方式。

核心功能:
- 启动和停止网格交易
- 查询账户信息
- 获取和取消订单
- 获取机器人状态
"""

import json
import logging
from typing import Any, Dict, List

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WeexBotBrowserController:
    """通过执行JavaScript与浏览器中的weexBot油猴脚本交互的控制器。"""

    def __init__(self, browser_tool):
        """
        初始化控制器。

        Args:
            browser_tool: 用于执行浏览器操作的工具实例 (例如 default_api)。
        """
        self.browser = browser_tool
        logger.info("WEEX 浏览器控制器已初始化")

    async def _execute_js(self, script: str) -> Any:
        """
        在浏览器中执行JavaScript并返回结果。

        Args:
            script: 要执行的JavaScript代码。

        Returns:
            执行结果，通常是一个字典。
        """
        try:
            # 注意：实际调用时，这里会是一个工具调用
            # result = self.browser.console_exec(brief="Executing bot command", javascript=script)
            # 为简化本地测试，我们模拟这个调用
            logger.info(f"准备执行JS: {script}")
            # 在实际 Manus 环境中，下面这行应替换为真正的工具调用
            # return f"(Simulated result for: {script})"
            
            # 实际工具调用
            result = await self.browser.console_exec(
                brief="与WEEX Bot交互",
                javascript=script
            )
            
            # 假设返回的是一个包含JSON字符串的字典
            output = result.get("output", "{}")
            # 清理和解析JSON
            if output.startswith("<"): # 移除可能的XML/HTML标签
                output = output.split(">", 1)[-1].rsplit("<", 1)[0]
            
            return json.loads(output)

        except Exception as e:
            logger.error(f"执行JavaScript失败: {e}")
            logger.error(f"失败的脚本: {script}")
            return {"error": str(e)}

    async def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息。"""
        logger.info("正在调用: getAccountInfo")
        script = "window.weexBot.getAccountInfo()"
        return await self._execute_js(f"JSON.stringify({script})")

    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """获取当前所有委托订单。"""
        logger.info("正在调用: getOpenOrders")
        script = "window.weexBot.getOpenOrders()"
        return await self._execute_js(f"JSON.stringify({script})")

    async def cancel_all_orders(self) -> Dict[str, Any]:
        """一键撤销所有订单。"""
        logger.info("正在调用: cancelAllOrders")
        script = "window.weexBot.cancelAllOrders()"
        return await self._execute_js(f"JSON.stringify({script})")

    async def start_grid_trading(self) -> Dict[str, Any]:
        """启动网格交易。"""
        logger.info("正在调用: startGrid")
        script = "window.weexBot.startGrid()"
        return await self._execute_js(f"JSON.stringify({script})")

    async def get_stats(self) -> Dict[str, Any]:
        """获取机器人运行的统计信息。"""
        logger.info("正在调用: getStats")
        script = "window.weexBot.getStats()"
        return await self._execute_js(f"JSON.stringify({script})")

    async def reset_state(self) -> None:
        """重置脚本状态。"""
        logger.info("正在调用: reset")
        script = "window.weexBot.reset()"
        await self._execute_js(script) # 此函数无返回值
        logger.info("机器人状态已重置")


# --- 模拟使用的示例 ---
# 在实际的 Manus Agent 环境中，你将通过 default_api 来调用浏览器工具
# 这个 main 函数仅用于演示控制器的结构和用法
async def main_demo(controller):
    """演示如何使用控制器。"""
    logger.info("\n===== 开始演示 WEEX Bot 控制器 =====")

    # 1. 获取账户信息
    logger.info("\n--- 步骤 1: 获取账户信息 ---")
    account_info = await controller.get_account_info()
    logger.info(f"账户信息: {account_info}")
    await asyncio.sleep(1)

    # 2. 获取当前委托
    logger.info("\n--- 步骤 2: 获取当前委托 ---")
    open_orders = await controller.get_open_orders()
    logger.info(f"当前有 {len(open_orders)} 个委托订单")
    if open_orders:
        logger.info(f"第一个订单: {open_orders[0]}")
    await asyncio.sleep(1)

    # 3. 启动网格交易
    logger.info("\n--- 步骤 3: 启动网格交易 ---")
    grid_stats = await controller.start_grid_trading()
    logger.info(f"网格交易已启动，统计: {grid_stats}")
    await asyncio.sleep(10) # 等待网格交易执行

    # 4. 获取最新统计
    logger.info("\n--- 步骤 4: 获取最新统计 ---")
    stats = await controller.get_stats()
    logger.info(f"最新统计: {stats}")
    await asyncio.sleep(1)

    # 5. 撤销所有订单
    logger.info("\n--- 步骤 5: 一键撤销所有订单 ---")
    cancel_result = await controller.cancel_all_orders()
    logger.info(f"撤单结果: {cancel_result}")

    logger.info("\n===== 演示结束 =====")


if __name__ == '__main__':
    # 这是一个模拟运行，无法在本地直接执行，因为它需要一个
    # 已经注入了油猴脚本并由 Manus Agent 控制的浏览器环境。
    
    # 伪造一个 browser_tool 对象用于演示
    class MockBrowser:
        async def console_exec(self, brief, javascript):
            print(f"[MockBrowser] Executing: {javascript}")
            # 模拟不同的返回值
            if "getAccountInfo" in javascript:
                return {"output": json.dumps({"available": "1000 USDT"})}
            if "getOpenOrders" in javascript:
                return {"output": json.dumps([{"symbol": "BTC/USDT", "price": "87000"}])}
            if "startGrid" in javascript:
                return {"output": json.dumps({"totalPlaced": 10, "status": "completed"})}
            return {"output": "{}"}

    async def run_mock_test():
        mock_browser = MockBrowser()
        controller = WeexBotBrowserController(mock_browser)
        await main_demo(controller)

    asyncio.run(run_mock_test())
