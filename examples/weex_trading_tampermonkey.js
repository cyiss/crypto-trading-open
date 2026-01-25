// ==UserScript==
// @name         WEEX Trading Bot - 网格交易脚本
// @namespace    http://tampermonkey.net/
// @version      1.0.0
// @description  通过 Tampermonkey 在 WEEX 上执行网格交易
// @author       Manus Trading Bot
// @match        https://www.weex.com/*
// @match        https://api-contract.weex.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_notification
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        unsafeWindow
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    // ============================================================
    // 配置部分
    // ============================================================
    const CONFIG = {
        apiKey: 'weex_d0649c112185fb5a0aeb13846fe915ac',
        apiSecret: 'a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61',
        apiPassphrase: 'manus20260125',
        baseUrl: 'https://api-contract.weex.com',
    };

    // ============================================================
    // 工具函数
    // ============================================================

    /**
     * 生成 HMAC-SHA256 签名
     */
    async function generateSignature(message, secret) {
        const encoder = new TextEncoder();
        const data = encoder.encode(message);
        const keyData = encoder.encode(secret);
        
        const key = await crypto.subtle.importKey(
            'raw',
            keyData,
            { name: 'HMAC', hash: 'SHA-256' },
            false,
            ['sign']
        );
        
        const signature = await crypto.subtle.sign('HMAC', key, data);
        
        // 转换为 Base64
        const bytes = new Uint8Array(signature);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }

    /**
     * 发送 API 请求
     */
    async function apiRequest(method, endpoint, data = null) {
        const timestamp = Date.now();
        const message = timestamp + endpoint;
        const signature = await generateSignature(message, CONFIG.apiSecret);

        const headers = {
            'ACCESS-KEY': CONFIG.apiKey,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': timestamp.toString(),
            'ACCESS-PASSPHRASE': CONFIG.apiPassphrase,
            'Content-Type': 'application/json',
        };

        const options = {
            method: method,
            headers: headers,
            url: CONFIG.baseUrl + endpoint,
        };

        if (data && (method === 'POST' || method === 'PUT')) {
            options.data = JSON.stringify(data);
        }

        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                ...options,
                onload: function(response) {
                    try {
                        const result = JSON.parse(response.responseText);
                        resolve({
                            status: response.status,
                            data: result,
                        });
                    } catch (e) {
                        resolve({
                            status: response.status,
                            data: response.responseText,
                        });
                    }
                },
                onerror: function(error) {
                    reject(error);
                },
            });
        });
    }

    /**
     * 获取账户信息
     */
    async function getAccountInfo() {
        console.log('[WEEX Bot] 获取账户信息...');
        try {
            const response = await apiRequest('GET', '/capi/v2/account/getAccounts');
            console.log('[WEEX Bot] 账户信息:', response);
            return response;
        } catch (error) {
            console.error('[WEEX Bot] 获取账户信息失败:', error);
            throw error;
        }
    }

    /**
     * 获取行情数据
     */
    async function getTicker(symbol) {
        console.log(`[WEEX Bot] 获取 ${symbol} 行情...`);
        try {
            const response = await apiRequest('GET', `/capi/v2/market/ticker?symbol=${symbol}`);
            console.log(`[WEEX Bot] ${symbol} 行情:`, response);
            return response;
        } catch (error) {
            console.error(`[WEEX Bot] 获取 ${symbol} 行情失败:`, error);
            throw error;
        }
    }

    /**
     * 下单
     */
    async function placeOrder(symbol, size, type, price, orderType = '0', matchPrice = '0') {
        console.log(`[WEEX Bot] 下单: ${symbol} ${size} ${type} @ ${price}`);
        
        const orderData = {
            symbol: symbol,
            client_oid: generateClientOid(),
            size: size,
            type: type,  // 1:开多 2:开空 3:平多 4:平空
            order_type: orderType,  // 0:普通 1:只做maker 2:全部成交或立即取消 3:立即成交并取消剩余
            match_price: matchPrice,  // 0:限价 1:市价
            price: price,
        };

        try {
            const response = await apiRequest('POST', '/capi/v2/order/placeOrder', orderData);
            console.log('[WEEX Bot] 下单结果:', response);
            return response;
        } catch (error) {
            console.error('[WEEX Bot] 下单失败:', error);
            throw error;
        }
    }

    /**
     * 撤单
     */
    async function cancelOrder(symbol, orderId) {
        console.log(`[WEEX Bot] 撤单: ${symbol} ${orderId}`);
        
        const cancelData = {
            symbol: symbol,
            order_id: orderId,
        };

        try {
            const response = await apiRequest('POST', '/capi/v2/order/cancelOrder', cancelData);
            console.log('[WEEX Bot] 撤单结果:', response);
            return response;
        } catch (error) {
            console.error('[WEEX Bot] 撤单失败:', error);
            throw error;
        }
    }

    /**
     * 生成客户端订单 ID
     */
    function generateClientOid() {
        return 'weex_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * 执行网格交易
     */
    async function executeGridTrading(symbol, gridLevels = 5, gridSpacing = 1000) {
        console.log(`[WEEX Bot] 开始网格交易: ${symbol}`);
        
        try {
            // 1. 获取当前价格
            const tickerResponse = await getTicker(symbol);
            if (tickerResponse.status !== 200) {
                throw new Error('获取行情失败');
            }

            const currentPrice = parseFloat(tickerResponse.data.last);
            console.log(`[WEEX Bot] 当前价格: ${currentPrice}`);

            // 2. 计算网格价格
            const buyPrices = [];
            const sellPrices = [];

            for (let i = 1; i <= gridLevels; i++) {
                buyPrices.push(currentPrice - (gridSpacing * i));
                sellPrices.push(currentPrice + (gridSpacing * i));
            }

            console.log('[WEEX Bot] 买入价格:', buyPrices);
            console.log('[WEEX Bot] 卖出价格:', sellPrices);

            // 3. 下单
            const orders = [];

            // 下买单
            for (let i = 0; i < buyPrices.length; i++) {
                try {
                    const result = await placeOrder(
                        symbol,
                        '0.01',  // 数量
                        '1',     // 1:开多
                        buyPrices[i].toString(),
                        '0',     // 普通订单
                        '0'      // 限价
                    );
                    orders.push(result);
                    console.log(`[WEEX Bot] 买单 ${i + 1} 下单成功`);
                } catch (error) {
                    console.error(`[WEEX Bot] 买单 ${i + 1} 下单失败:`, error);
                }
            }

            // 下卖单
            for (let i = 0; i < sellPrices.length; i++) {
                try {
                    const result = await placeOrder(
                        symbol,
                        '0.01',  // 数量
                        '2',     // 2:开空
                        sellPrices[i].toString(),
                        '0',     // 普通订单
                        '0'      // 限价
                    );
                    orders.push(result);
                    console.log(`[WEEX Bot] 卖单 ${i + 1} 下单成功`);
                } catch (error) {
                    console.error(`[WEEX Bot] 卖单 ${i + 1} 下单失败:`, error);
                }
            }

            console.log('[WEEX Bot] 网格交易完成');
            return orders;

        } catch (error) {
            console.error('[WEEX Bot] 网格交易失败:', error);
            throw error;
        }
    }

    // ============================================================
    // 暴露到全局作用域
    // ============================================================
    window.WEEXBot = {
        getAccountInfo,
        getTicker,
        placeOrder,
        cancelOrder,
        executeGridTrading,
        generateSignature,
        apiRequest,
    };

    // ============================================================
    // 创建控制面板
    // ============================================================
    function createControlPanel() {
        const panel = document.createElement('div');
        panel.id = 'weex-bot-panel';
        panel.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 400px;
            background: #1a1a1a;
            border: 2px solid #00ff00;
            border-radius: 8px;
            padding: 20px;
            font-family: monospace;
            color: #00ff00;
            z-index: 10000;
            box-shadow: 0 0 20px rgba(0, 255, 0, 0.3);
        `;

        panel.innerHTML = `
            <div style="margin-bottom: 10px; font-weight: bold; font-size: 14px;">
                🤖 WEEX Trading Bot
            </div>
            <div style="margin-bottom: 10px; font-size: 12px;">
                <button id="btn-account" style="
                    background: #00ff00;
                    color: #000;
                    border: none;
                    padding: 8px 12px;
                    margin: 5px 5px 5px 0;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: bold;
                ">获取账户</button>
                
                <button id="btn-ticker" style="
                    background: #00ff00;
                    color: #000;
                    border: none;
                    padding: 8px 12px;
                    margin: 5px 5px 5px 0;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: bold;
                ">获取行情</button>
                
                <button id="btn-grid" style="
                    background: #00ff00;
                    color: #000;
                    border: none;
                    padding: 8px 12px;
                    margin: 5px 5px 5px 0;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: bold;
                ">网格交易</button>
            </div>
            <div id="bot-output" style="
                background: #000;
                border: 1px solid #00ff00;
                padding: 10px;
                height: 200px;
                overflow-y: auto;
                font-size: 11px;
                margin-top: 10px;
            "></div>
            <div style="margin-top: 10px; font-size: 11px; color: #888;">
                在浏览器控制台使用: window.WEEXBot
            </div>
        `;

        document.body.appendChild(panel);

        // 事件监听
        document.getElementById('btn-account').addEventListener('click', async () => {
            appendOutput('正在获取账户信息...');
            try {
                const result = await window.WEEXBot.getAccountInfo();
                appendOutput('账户信息获取成功: ' + JSON.stringify(result).substring(0, 100));
            } catch (error) {
                appendOutput('错误: ' + error.message);
            }
        });

        document.getElementById('btn-ticker').addEventListener('click', async () => {
            appendOutput('正在获取行情...');
            try {
                const result = await window.WEEXBot.getTicker('cmt_btcusdt');
                appendOutput('行情获取成功: ' + JSON.stringify(result).substring(0, 100));
            } catch (error) {
                appendOutput('错误: ' + error.message);
            }
        });

        document.getElementById('btn-grid').addEventListener('click', async () => {
            appendOutput('正在执行网格交易...');
            try {
                const result = await window.WEEXBot.executeGridTrading('cmt_btcusdt', 5, 1000);
                appendOutput('网格交易完成: ' + result.length + ' 个订单');
            } catch (error) {
                appendOutput('错误: ' + error.message);
            }
        });
    }

    /**
     * 添加输出日志
     */
    function appendOutput(message) {
        const output = document.getElementById('bot-output');
        if (output) {
            const timestamp = new Date().toLocaleTimeString();
            output.innerHTML += `[${timestamp}] ${message}\n`;
            output.scrollTop = output.scrollHeight;
        }
        console.log('[WEEX Bot]', message);
    }

    // ============================================================
    // 初始化
    // ============================================================
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createControlPanel);
    } else {
        createControlPanel();
    }

    console.log('[WEEX Bot] 脚本已加载');
    console.log('[WEEX Bot] 使用方法: window.WEEXBot.getAccountInfo()');
    console.log('[WEEX Bot] 使用方法: window.WEEXBot.getTicker("cmt_btcusdt")');
    console.log('[WEEX Bot] 使用方法: window.WEEXBot.executeGridTrading("cmt_btcusdt", 5, 1000)');

})();
