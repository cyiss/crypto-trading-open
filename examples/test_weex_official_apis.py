#!/usr/bin/env python3
"""
测试 WEEX 官方接口

根据官方文档：
- 获取账户信息列表: GET /capi/v2/account/getAccounts
- 下单: POST /capi/v2/order/placeOrder
"""

import asyncio
import hashlib
import hmac
import base64
import json
import uuid
from datetime import datetime, timezone

import aiohttp


async def test_get_accounts():
    """测试获取账户信息列表接口"""
    
    api_key = "weex_d0649c112185fb5a0aeb13846fe915ac"
    api_secret = "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
    api_passphrase = "manus20260125"
    
    endpoint = "/capi/v2/account/getAccounts"
    
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
        "locale": "zh-CN",
    }
    
    url = f"https://api-contract.weex.com{endpoint}"
    
    print("=" * 100)
    print("测试 1: 获取账户信息列表")
    print("=" * 100)
    print(f"\n请求: GET {endpoint}")
    print(f"URL: {url}")
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, headers=headers) as resp:
                body = await resp.text()
                
                print(f"\n状态码: {resp.status}")
                print(f"状态文本: {resp.reason}")
                
                if body:
                    try:
                        json_data = json.loads(body)
                        print(f"\n响应 (JSON):")
                        print(json.dumps(json_data, indent=2, ensure_ascii=False)[:500])
                    except:
                        print(f"\n响应 (文本):")
                        print(body[:500])
                else:
                    print(f"\n响应: (空)")
                
                if resp.status == 200:
                    print("\n✓ 成功！")
                else:
                    print(f"\n✗ 失败 (状态码: {resp.status})")
        
        except Exception as e:
            print(f"\n✗ 请求异常: {e}")


async def test_place_order():
    """测试下单接口"""
    
    api_key = "weex_d0649c112185fb5a0aeb13846fe915ac"
    api_secret = "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
    api_passphrase = "manus20260125"
    
    endpoint = "/capi/v2/order/placeOrder"
    
    # 构造请求体
    order_data = {
        "symbol": "cmt_btcusdt",
        "client_oid": str(uuid.uuid4())[:40],  # 最多 40 个字符
        "size": "0.01",
        "type": "1",  # 开多
        "order_type": "0",  # 普通订单
        "match_price": "0",  # 限价
        "price": "50000",  # 测试价格（远低于市价，不会成交）
    }
    
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
        "locale": "zh-CN",
    }
    
    url = f"https://api-contract.weex.com{endpoint}"
    
    print("\n\n" + "=" * 100)
    print("测试 2: 下单")
    print("=" * 100)
    print(f"\n请求: POST {endpoint}")
    print(f"URL: {url}")
    print(f"\n请求体:")
    print(json.dumps(order_data, indent=2, ensure_ascii=False))
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.post(url, headers=headers, json=order_data) as resp:
                body = await resp.text()
                
                print(f"\n状态码: {resp.status}")
                print(f"状态文本: {resp.reason}")
                
                if body:
                    try:
                        json_data = json.loads(body)
                        print(f"\n响应 (JSON):")
                        print(json.dumps(json_data, indent=2, ensure_ascii=False))
                    except:
                        print(f"\n响应 (文本):")
                        print(body[:500])
                else:
                    print(f"\n响应: (空)")
                
                if resp.status == 200:
                    print("\n✓ 成功！")
                else:
                    print(f"\n✗ 失败 (状态码: {resp.status})")
        
        except Exception as e:
            print(f"\n✗ 请求异常: {e}")


async def test_other_account_endpoints():
    """测试其他账户接口"""
    
    api_key = "weex_d0649c112185fb5a0aeb13846fe915ac"
    api_secret = "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
    api_passphrase = "manus20260125"
    
    endpoints = [
        ("/capi/v2/account/getAccounts", "GET", "获取账户信息列表"),
        ("/capi/v2/account/getAccount", "GET", "获取单个币种账户信息"),
        ("/capi/v2/account/getAssets", "GET", "获取账户资产"),
        ("/capi/v2/account/getBalance", "GET", "获取账户余额"),
    ]
    
    print("\n\n" + "=" * 100)
    print("测试 3: 其他账户接口")
    print("=" * 100 + "\n")
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for endpoint, method, desc in endpoints:
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
                "locale": "zh-CN",
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
                print(f"{status_icon} {method:4s} {endpoint:40s} → {status}")
                
                if status < 400 and body:
                    try:
                        json_data = json.loads(body)
                        json_str = json.dumps(json_data, ensure_ascii=False)
                        if len(json_str) > 100:
                            print(f"     {json_str[:100]}...")
                        else:
                            print(f"     {json_str}")
                    except:
                        print(f"     {body[:100]}")
                elif status >= 400 and not body:
                    print(f"     (空响应)")
            
            except Exception as e:
                print(f"✗ {method:4s} {endpoint:40s} → 错误: {e}")


if __name__ == "__main__":
    asyncio.run(test_get_accounts())
    asyncio.run(test_place_order())
    asyncio.run(test_other_account_endpoints())
