#!/usr/bin/env python3
"""
测试 WEEX 新的账户接口

新接口：GET /capi/v2/account/getAccounts
"""

import asyncio
import hashlib
import hmac
import base64
import json
from datetime import datetime, timezone

import aiohttp


async def test_getAccounts():
    """测试新的 getAccounts 接口"""
    
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
    }
    
    url = f"https://api-contract.weex.com{endpoint}"
    
    print("=" * 100)
    print("测试新的账户接口: GET /capi/v2/account/getAccounts")
    print("=" * 100)
    
    print(f"\n[请求信息]")
    print(f"  方法: GET")
    print(f"  URL: {url}")
    print(f"  时间: {datetime.now(timezone.utc).isoformat()}")
    
    print(f"\n[请求头]")
    for key, value in headers.items():
        if key == "ACCESS-SIGN":
            print(f"  {key}: {value[:30]}...{value[-20:]}")
        else:
            print(f"  {key}: {value}")
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, headers=headers) as resp:
                body = await resp.text()
                
                print(f"\n[响应信息]")
                print(f"  状态码: {resp.status}")
                print(f"  状态文本: {resp.reason}")
                
                print(f"\n[响应头]")
                for key, value in resp.headers.items():
                    print(f"  {key}: {value}")
                
                print(f"\n[响应体]")
                if body:
                    try:
                        json_data = json.loads(body)
                        print(json.dumps(json_data, indent=2, ensure_ascii=False))
                    except:
                        print(body)
                else:
                    print("(空)")
                
                # 分析结果
                print(f"\n[结果分析]")
                if resp.status == 200:
                    print("✓ 成功！接口工作正常")
                elif resp.status == 521:
                    print("✗ 返回 521 错误")
                else:
                    print(f"? 返回其他状态码: {resp.status}")
        
        except Exception as e:
            print(f"\n✗ 请求失败: {e}")
            import traceback
            traceback.print_exc()


async def test_related_endpoints():
    """测试相关的新接口"""
    
    api_key = "weex_d0649c112185fb5a0aeb13846fe915ac"
    api_secret = "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
    api_passphrase = "manus20260125"
    
    # 基于新接口命名规则推测的其他接口
    endpoints = [
        "/capi/v2/account/getAccounts",  # 获取账户信息列表
        "/capi/v2/account/getAccount",   # 获取单个币种账户信息（可能）
        "/capi/v2/account/getAssets",    # 获取账户资产（可能）
        "/capi/v2/account/assets",       # 获取账户资产（可能）
    ]
    
    print("\n\n" + "=" * 100)
    print("测试相关的新接口")
    print("=" * 100 + "\n")
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for endpoint in endpoints:
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
                    
                    status_icon = "✓" if resp.status < 400 else "✗"
                    print(f"{status_icon} {endpoint}")
                    print(f"  状态: {resp.status}")
                    
                    if body:
                        try:
                            json_data = json.loads(body)
                            # 只显示前 200 字符
                            json_str = json.dumps(json_data, ensure_ascii=False)
                            if len(json_str) > 200:
                                print(f"  响应: {json_str[:200]}...")
                            else:
                                print(f"  响应: {json_str}")
                        except:
                            print(f"  响应: {body[:200]}")
                    else:
                        print(f"  响应: (空)")
                    
                    print()
            
            except Exception as e:
                print(f"✗ {endpoint}")
                print(f"  错误: {e}")
                print()


if __name__ == "__main__":
    asyncio.run(test_getAccounts())
    asyncio.run(test_related_endpoints())
