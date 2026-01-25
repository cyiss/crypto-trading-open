#!/usr/bin/env python3
"""
详细捕获 WEEX API 521 错误响应

捕获完整的 HTTP 响应，包括：
- 响应状态码
- 响应头（所有字段）
- 响应体（原始字节和文本）
- 响应时间
- 连接信息
"""

import asyncio
import hashlib
import hmac
import base64
import json
from datetime import datetime, timezone
from typing import Optional

import aiohttp


async def capture_521_response_detailed():
    """详细捕获 521 错误响应"""
    
    # 凭证
    api_key = "weex_d0649c112185fb5a0aeb13846fe915ac"
    api_secret = "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
    api_passphrase = "manus20260125"
    
    # 生成签名
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    request_path = "/capi/v2/account/info"
    
    message = str(timestamp) + request_path
    signature = hmac.new(
        api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    # 构造请求头
    headers = {
        "ACCESS-KEY": api_key,
        "ACCESS-SIGN": signature_b64,
        "ACCESS-TIMESTAMP": str(timestamp),
        "ACCESS-PASSPHRASE": api_passphrase,
        "Content-Type": "application/json",
        "User-Agent": "Python-WEEX-SDK/1.0",
    }
    
    url = "https://api-contract.weex.com/capi/v2/account/info"
    
    print("=" * 100)
    print("WEEX API 521 错误响应详细捕获")
    print("=" * 100)
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
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
        
        try:
            async with session.get(url, headers=headers) as resp:
                # 记录响应时间
                response_time = datetime.now(timezone.utc).isoformat()
                
                # 获取响应头
                response_headers = dict(resp.headers)
                
                # 读取响应体（原始字节）
                response_body_bytes = await resp.content.read()
                response_body_text = response_body_bytes.decode('utf-8', errors='replace')
                
                # 打印响应信息
                print(f"\n[响应信息]")
                print(f"  状态码: {resp.status}")
                print(f"  状态文本: {resp.reason}")
                print(f"  响应时间: {response_time}")
                print(f"  响应大小: {len(response_body_bytes)} 字节")
                
                print(f"\n[响应头]")
                for key, value in response_headers.items():
                    print(f"  {key}: {value}")
                
                print(f"\n[响应体 - 原始字节]")
                print(f"  长度: {len(response_body_bytes)} 字节")
                if response_body_bytes:
                    print(f"  十六进制: {response_body_bytes.hex()}")
                else:
                    print(f"  (空)")
                
                print(f"\n[响应体 - 文本]")
                if response_body_text:
                    print(f"  内容: '{response_body_text}'")
                    print(f"  长度: {len(response_body_text)} 字符")
                    
                    # 尝试解析为 JSON
                    try:
                        json_data = json.loads(response_body_text)
                        print(f"\n[响应体 - JSON 解析]")
                        print(json.dumps(json_data, indent=2, ensure_ascii=False))
                    except json.JSONDecodeError as e:
                        print(f"  (不是有效的 JSON: {e})")
                else:
                    print(f"  (空)")
                
                # 分析响应
                print(f"\n[响应分析]")
                print(f"  HTTP 状态: {resp.status}")
                print(f"  是否成功: {resp.status < 400}")
                print(f"  是否错误: {resp.status >= 400}")
                print(f"  是否 521: {resp.status == 521}")
                
                # 检查关键响应头
                print(f"\n[关键响应头检查]")
                print(f"  Server: {response_headers.get('Server', '(未设置)')}")
                print(f"  Content-Type: {response_headers.get('Content-Type', '(未设置)')}")
                print(f"  Content-Length: {response_headers.get('Content-Length', '(未设置)')}")
                print(f"  Connection: {response_headers.get('Connection', '(未设置)')}")
                print(f"  Date: {response_headers.get('Date', '(未设置)')}")
                print(f"  X-Request-Id: {response_headers.get('X-Request-Id', '(未设置)')}")
                print(f"  X-Trace-Id: {response_headers.get('X-Trace-Id', '(未设置)')}")
                
                # 尝试其他端点
                print(f"\n" + "=" * 100)
                print("测试其他私有 API 端点")
                print("=" * 100)
                
                endpoints = [
                    "/capi/v2/account/balance",
                    "/capi/v2/account/positions",
                    "/capi/v2/orders",
                    "/capi/v1/account/info",  # 尝试 v1 版本
                    "/api/v2/account/info",   # 尝试不同的路径
                ]
                
                for endpoint in endpoints:
                    # 重新生成签名
                    ts = int(datetime.now(timezone.utc).timestamp() * 1000)
                    msg = str(ts) + endpoint
                    sig = hmac.new(
                        api_secret.encode('utf-8'),
                        msg.encode('utf-8'),
                        hashlib.sha256
                    ).digest()
                    sig_b64 = base64.b64encode(sig).decode('utf-8')
                    
                    hdrs = {
                        "ACCESS-KEY": api_key,
                        "ACCESS-SIGN": sig_b64,
                        "ACCESS-TIMESTAMP": str(ts),
                        "ACCESS-PASSPHRASE": api_passphrase,
                        "Content-Type": "application/json",
                    }
                    
                    endpoint_url = f"https://api-contract.weex.com{endpoint}"
                    
                    try:
                        async with session.get(endpoint_url, headers=hdrs) as ep_resp:
                            status_icon = "✓" if ep_resp.status < 400 else "✗"
                            body = await ep_resp.text()
                            body_preview = body[:100] if body else "(空)"
                            print(f"{status_icon} {endpoint}")
                            print(f"    状态: {ep_resp.status}")
                            print(f"    响应: {body_preview}")
                    except Exception as e:
                        print(f"✗ {endpoint}")
                        print(f"    错误: {e}")
        
        except asyncio.TimeoutError:
            print("❌ 请求超时")
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n" + "=" * 100)
    print("捕获完成")
    print("=" * 100)


async def test_with_curl_simulation():
    """使用 curl 模拟的请求方式测试"""
    
    print("\n\n" + "=" * 100)
    print("使用 curl 模拟请求")
    print("=" * 100)
    
    api_key = "weex_d0649c112185fb5a0aeb13846fe915ac"
    api_secret = "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
    api_passphrase = "manus20260125"
    
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    request_path = "/capi/v2/account/info"
    
    message = str(timestamp) + request_path
    signature = hmac.new(
        api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    # 生成 curl 命令
    curl_cmd = f"""curl -X GET "https://api-contract.weex.com/capi/v2/account/info" \\
  -H "ACCESS-KEY: {api_key}" \\
  -H "ACCESS-SIGN: {signature_b64}" \\
  -H "ACCESS-TIMESTAMP: {timestamp}" \\
  -H "ACCESS-PASSPHRASE: {api_passphrase}" \\
  -H "Content-Type: application/json" \\
  -v"""
    
    print("\n[等效的 curl 命令]")
    print(curl_cmd)
    
    print("\n[执行 curl 命令...]")
    import subprocess
    result = subprocess.run(
        curl_cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=30
    )
    
    print("\n[curl 标准输出]")
    print(result.stdout)
    
    print("\n[curl 标准错误]")
    print(result.stderr)


if __name__ == "__main__":
    asyncio.run(capture_521_response_detailed())
    asyncio.run(test_with_curl_simulation())
