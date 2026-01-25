#!/usr/bin/env python3
"""
伪装成真实用户的 WEEX API 请求

添加真实的浏览器 User-Agent 和其他请求头，
使请求看起来像来自真实用户的浏览器请求
"""

import asyncio
import hashlib
import hmac
import base64
import json
import uuid
from datetime import datetime, timezone

import aiohttp


# 真实的浏览器 User-Agent 列表
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


def get_real_user_headers(api_key, api_secret, api_passphrase, timestamp, endpoint):
    """
    生成看起来像真实用户的请求头
    """
    
    # 生成签名
    message = str(timestamp) + endpoint
    signature = hmac.new(
        api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    headers = {
        # API 认证头
        "ACCESS-KEY": api_key,
        "ACCESS-SIGN": signature_b64,
        "ACCESS-TIMESTAMP": str(timestamp),
        "ACCESS-PASSPHRASE": api_passphrase,
        
        # 真实浏览器请求头
        "User-Agent": USER_AGENTS[0],  # Chrome on Windows
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "Origin": "https://www.weex.com",
        "Referer": "https://www.weex.com/",
        
        # 其他常见请求头
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Connection": "keep-alive",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }
    
    return headers


async def test_with_real_user_headers():
    """使用真实用户头测试 API"""
    
    api_key = "weex_d0649c112185fb5a0aeb13846fe915ac"
    api_secret = "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
    api_passphrase = "manus20260125"
    
    endpoints = [
        ("/capi/v2/account/getAccounts", "GET", "获取账户信息列表"),
        ("/capi/v2/order/placeOrder", "POST", "下单"),
    ]
    
    print("=" * 100)
    print("使用真实用户请求头测试 WEEX API")
    print("=" * 100)
    print("\n伪装成真实浏览器用户的请求...\n")
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    # 创建自定义连接器，支持更多的 HTTP 特性
    connector = aiohttp.TCPConnector(
        ssl=True,
        enable_cleanup_closed=True,
        force_close=False,
    )
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        for endpoint, method, desc in endpoints:
            timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
            headers = get_real_user_headers(api_key, api_secret, api_passphrase, timestamp, endpoint)
            
            url = f"https://api-contract.weex.com{endpoint}"
            
            print(f"\n[测试] {desc}")
            print(f"  方法: {method}")
            print(f"  路径: {endpoint}")
            print(f"  URL: {url}")
            
            print(f"\n  请求头:")
            for key, value in headers.items():
                if key == "ACCESS-SIGN":
                    print(f"    {key}: {value[:30]}...{value[-20:]}")
                elif key == "User-Agent":
                    print(f"    {key}: {value[:60]}...")
                else:
                    print(f"    {key}: {value}")
            
            try:
                if method == "GET":
                    async with session.get(url, headers=headers) as resp:
                        body = await resp.text()
                        status = resp.status
                else:
                    order_data = {
                        "symbol": "cmt_btcusdt",
                        "client_oid": str(uuid.uuid4())[:40],
                        "size": "0.01",
                        "type": "1",
                        "order_type": "0",
                        "match_price": "0",
                        "price": "50000",
                    }
                    async with session.post(url, headers=headers, json=order_data) as resp:
                        body = await resp.text()
                        status = resp.status
                
                print(f"\n  响应状态: {status}")
                
                if body:
                    try:
                        json_data = json.loads(body)
                        print(f"  响应 (JSON):")
                        json_str = json.dumps(json_data, indent=4, ensure_ascii=False)
                        if len(json_str) > 500:
                            print(f"    {json_str[:500]}...")
                        else:
                            print(f"    {json_str}")
                    except:
                        print(f"  响应 (文本):")
                        if len(body) > 500:
                            print(f"    {body[:500]}...")
                        else:
                            print(f"    {body}")
                else:
                    print(f"  响应: (空)")
                
                if status == 200:
                    print(f"\n  ✓ 成功！")
                else:
                    print(f"\n  ✗ 失败 (状态码: {status})")
            
            except Exception as e:
                print(f"\n  ✗ 请求异常: {e}")
                import traceback
                traceback.print_exc()


async def test_with_different_user_agents():
    """使用不同的 User-Agent 测试"""
    
    api_key = "weex_d0649c112185fb5a0aeb13846fe915ac"
    api_secret = "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
    api_passphrase = "manus20260125"
    
    endpoint = "/capi/v2/account/getAccounts"
    url = f"https://api-contract.weex.com{endpoint}"
    
    print("\n\n" + "=" * 100)
    print("使用不同的 User-Agent 测试")
    print("=" * 100 + "\n")
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for i, user_agent in enumerate(USER_AGENTS, 1):
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
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://www.weex.com",
                "Referer": "https://www.weex.com/",
            }
            
            try:
                async with session.get(url, headers=headers) as resp:
                    body = await resp.text()
                    status = resp.status
                    
                    status_icon = "✓" if status < 400 else "✗"
                    ua_preview = user_agent[:50] + "..." if len(user_agent) > 50 else user_agent
                    
                    print(f"{status_icon} [{i}] {ua_preview}")
                    print(f"    状态: {status}")
                    
                    if body:
                        print(f"    响应: {body[:100]}")
                    else:
                        print(f"    响应: (空)")
                    
                    print()
            
            except Exception as e:
                print(f"✗ [{i}] {user_agent[:50]}...")
                print(f"    错误: {e}")
                print()


async def test_with_session_cookies():
    """使用会话 Cookie 测试"""
    
    api_key = "weex_d0649c112185fb5a0aeb13846fe915ac"
    api_secret = "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
    api_passphrase = "manus20260125"
    
    endpoint = "/capi/v2/account/getAccounts"
    url = f"https://api-contract.weex.com{endpoint}"
    
    print("\n\n" + "=" * 100)
    print("使用会话 Cookie 测试")
    print("=" * 100 + "\n")
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    # 创建带有 Cookie jar 的会话
    async with aiohttp.ClientSession(timeout=timeout) as session:
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        message = str(timestamp) + endpoint
        signature = hmac.new(
            api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        headers = get_real_user_headers(api_key, api_secret, api_passphrase, timestamp, endpoint)
        
        # 添加模拟的会话 Cookie
        headers["Cookie"] = "session_id=test_session; path=/; domain=.weex.com"
        
        print("[请求信息]")
        print(f"  URL: {url}")
        print(f"  方法: GET")
        print(f"  包含 Cookie: 是")
        
        try:
            async with session.get(url, headers=headers) as resp:
                body = await resp.text()
                status = resp.status
                
                print(f"\n[响应信息]")
                print(f"  状态码: {status}")
                
                if body:
                    try:
                        json_data = json.loads(body)
                        print(f"  响应 (JSON):")
                        print(json.dumps(json_data, indent=2, ensure_ascii=False)[:300])
                    except:
                        print(f"  响应 (文本): {body[:300]}")
                else:
                    print(f"  响应: (空)")
                
                if status == 200:
                    print(f"\n✓ 成功！")
                else:
                    print(f"\n✗ 失败 (状态码: {status})")
        
        except Exception as e:
            print(f"\n✗ 请求异常: {e}")


if __name__ == "__main__":
    print("\n")
    asyncio.run(test_with_real_user_headers())
    asyncio.run(test_with_different_user_agents())
    asyncio.run(test_with_session_cookies())
