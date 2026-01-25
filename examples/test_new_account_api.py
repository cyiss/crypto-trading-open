#!/usr/bin/env python3
"""
测试 WEEX 新的账户接口

根据变更日志（2025-11-28），新的账户接口已上线：
- 最新获取账户信息列表接口
- 最新获取单个币种账户信息接口

老的接口已于 2025-12-01 下线：
- /capi/v2/account/accounts (已下线)
- /capi/v2/account/account (已下线)
"""

import asyncio
import hashlib
import hmac
import base64
import json
from datetime import datetime, timezone

import aiohttp


async def test_account_endpoints():
    """测试各种可能的账户接口"""
    
    api_key = "weex_d0649c112185fb5a0aeb13846fe915ac"
    api_secret = "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
    api_passphrase = "manus20260125"
    
    # 可能的账户接口路径
    endpoints = [
        # 原始尝试的接口
        "/capi/v2/account/info",
        
        # 已下线的接口
        "/capi/v2/account/accounts",
        "/capi/v2/account/account",
        
        # 可能的新接口（基于变更日志提示）
        "/capi/v2/accounts",
        "/capi/v2/account",
        "/capi/v2/account/list",
        "/capi/v2/account/accounts/list",
        
        # 其他可能的路径
        "/api/v2/account/info",
        "/api/v2/account",
        "/api/v2/accounts",
        
        # 交易接口
        "/capi/v2/trade/orders",
        "/capi/v2/orders",
        "/capi/v2/trade/order",
        
        # 其他可能性
        "/capi/v2/user/account",
        "/capi/v2/user/accounts",
    ]
    
    print("=" * 100)
    print("WEEX 账户接口测试")
    print("=" * 100)
    print("\n根据变更日志（2025-11-28）:")
    print("  • 新的账户接口已上线")
    print("  • 老的接口（/capi/v2/account/accounts, /capi/v2/account/account）已于 2025-12-01 下线")
    print("\n" + "=" * 100)
    print("测试各个端点...")
    print("=" * 100 + "\n")
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for endpoint in endpoints:
            # 生成签名
            timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
            message = str(timestamp) + endpoint
            signature = hmac.new(
                api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
            signature_b64 = base64.b64encode(signature).decode('utf-8')
            
            headers = {
                "ACCESS-KEY": api_key,
                "ACCESS-SIGN": signature_b64,
                "ACCESS-TIMESTAMP": str(timestamp),
                "ACCESS-PASSPHRASE": api_passphrase,
                "Content-Type": "application/json",
            }
            
            url = f"https://api-contract.weex.com{endpoint}"
            
            try:
                async with session.get(url, headers=headers) as resp:
                    body = await resp.text()
                    
                    # 判断状态
                    if resp.status < 400:
                        status_icon = "✓"
                        status_color = "\033[92m"  # 绿色
                    elif resp.status == 521:
                        status_icon = "✗"
                        status_color = "\033[91m"  # 红色
                    else:
                        status_icon = "?"
                        status_color = "\033[93m"  # 黄色
                    
                    reset_color = "\033[0m"
                    
                    # 打印结果
                    print(f"{status_color}{status_icon}{reset_color} {endpoint}")
                    print(f"  状态: {resp.status}")
                    
                    if body:
                        # 尝试解析 JSON
                        try:
                            json_data = json.loads(body)
                            print(f"  响应: {json.dumps(json_data, ensure_ascii=False)[:150]}")
                        except:
                            print(f"  响应: {body[:150]}")
                    else:
                        print(f"  响应: (空)")
                    
                    print()
            
            except Exception as e:
                print(f"✗ {endpoint}")
                print(f"  错误: {e}")
                print()


async def test_with_different_methods():
    """使用不同的 HTTP 方法测试"""
    
    api_key = "weex_d0649c112185fb5a0aeb13846fe915ac"
    api_secret = "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
    api_passphrase = "manus20260125"
    
    endpoints_to_test = [
        "/capi/v2/accounts",
        "/capi/v2/account",
        "/capi/v2/account/list",
    ]
    
    methods = ["GET", "POST"]
    
    print("\n" + "=" * 100)
    print("使用不同 HTTP 方法测试")
    print("=" * 100 + "\n")
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for endpoint in endpoints_to_test:
            for method in methods:
                timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
                message = str(timestamp) + endpoint
                signature = hmac.new(
                    api_secret.encode('utf-8'),
                    message.encode('utf-8'),
                    hashlib.sha256
                ).digest()
                signature_b64 = base64.b64encode(signature).decode('utf-8')
                
                headers = {
                    "ACCESS-KEY": api_key,
                    "ACCESS-SIGN": signature_b64,
                    "ACCESS-TIMESTAMP": str(timestamp),
                    "ACCESS-PASSPHRASE": api_passphrase,
                    "Content-Type": "application/json",
                }
                
                url = f"https://api-contract.weex.com{endpoint}"
                
                try:
                    if method == "GET":
                        async with session.get(url, headers=headers) as resp:
                            body = await resp.text()
                            status = resp.status
                    else:
                        async with session.post(url, headers=headers, json={}) as resp:
                            body = await resp.text()
                            status = resp.status
                    
                    status_icon = "✓" if status < 400 else "✗"
                    print(f"{status_icon} {method:4s} {endpoint:30s} → {status}")
                    
                    if body and status < 400:
                        try:
                            json_data = json.loads(body)
                            print(f"     {json.dumps(json_data, ensure_ascii=False)[:100]}")
                        except:
                            print(f"     {body[:100]}")
                
                except Exception as e:
                    print(f"✗ {method:4s} {endpoint:30s} → 错误: {e}")


if __name__ == "__main__":
    asyncio.run(test_account_endpoints())
    asyncio.run(test_with_different_methods())
