// ==UserScript==
// @name         WEEX Trading Bot - 可控制的网格交易脚本
// @namespace    http://tampermonkey.net/
// @version      2.0.0
// @description  通过 WebSocket/HTTP 被控制的 WEEX 网格交易脚本
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
        
        // 控制服务器配置
        controlServerUrl: 'ws://localhost:8765',  // WebSocket 服务器地址
        controlHttpUrl: 'http://localhost:8080',  // HTTP 服务器地址
        
        // 网格交易默认配置
        defaultSymbol: 'cmt_btcusdt',
        defaultGridLevels: 5,
        defaultGridSpacing: 1000,
    };

    // ============================================================
    // 全局状态
    // ============================================================
    let globalState = {
        isConnected: false,
        wsConnection: null,
        gridTrading: {
            isRunning: false,
            symbol: CONFIG.defaultSymbol,
            gridLevels: CONFIG.defaultGridLevels,
            gridSpacing: CONFIG.defaultGridSpacing,
            orders: [],
            currentPrice: 0,
        },
        stats: {
            totalOrders: 0,
            successfulOrders: 0,
            failedOrders: 0,
            totalProfit: 0,
        },
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
            if (response.status === 200 && response.data.last) {
                globalState.gridTrading.currentPrice = parseFloat(response.data.last);
            }
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
            type: type,
            order_type: orderType,
            match_price: matchPrice,
            price: price,
        };

        try {
            const response = await apiRequest('POST', '/capi/v2/order/placeOrder', orderData);
            
            globalState.stats.totalOrders++;
            if (response.status === 200) {
                globalState.stats.successfulOrders++;
                globalState.gridTrading.orders.push({
                    orderId: response.data.order_id,
                    clientOid: orderData.client_oid,
                    symbol: symbol,
                    size: size,
                    type: type,
                    price: price,
                    timestamp: Date.now(),
                });
            } else {
                globalState.stats.failedOrders++;
            }
            
            console.log('[WEEX Bot] 下单结果:', response);
            return response;
        } catch (error) {
            globalState.stats.failedOrders++;
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
    async function executeGridTrading(symbol, gridLevels, gridSpacing) {
        console.log(`[WEEX Bot] 开始网格交易: ${symbol}`);
        
        if (globalState.gridTrading.isRunning) {
            console.warn('[WEEX Bot] 网格交易已在运行中');
            return { error: '网格交易已在运行中' };
        }

        globalState.gridTrading.isRunning = true;
        globalState.gridTrading.symbol = symbol;
        globalState.gridTrading.gridLevels = gridLevels;
        globalState.gridTrading.gridSpacing = gridSpacing;
        globalState.gridTrading.orders = [];

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
                        '0.01',
                        '1',     // 开多
                        buyPrices[i].toString(),
                        '0',
                        '0'
                    );
                    orders.push(result);
                    console.log(`[WEEX Bot] 买单 ${i + 1} 下单成功`);
                    await sleep(500); // 延迟以避免速率限制
                } catch (error) {
                    console.error(`[WEEX Bot] 买单 ${i + 1} 下单失败:`, error);
                }
            }

            // 下卖单
            for (let i = 0; i < sellPrices.length; i++) {
                try {
                    const result = await placeOrder(
                        symbol,
                        '0.01',
                        '2',     // 开空
                        sellPrices[i].toString(),
                        '0',
                        '0'
                    );
                    orders.push(result);
                    console.log(`[WEEX Bot] 卖单 ${i + 1} 下单成功`);
                    await sleep(500); // 延迟以避免速率限制
                } catch (error) {
                    console.error(`[WEEX Bot] 卖单 ${i + 1} 下单失败:`, error);
                }
            }

            console.log('[WEEX Bot] 网格交易完成');
            globalState.gridTrading.isRunning = false;
            
            return {
                success: true,
                ordersPlaced: orders.length,
                stats: globalState.stats,
            };

        } catch (error) {
            console.error('[WEEX Bot] 网格交易失败:', error);
            globalState.gridTrading.isRunning = false;
            return { error: error.message };
        }
    }

    /**
     * 停止网格交易（撤销所有订单）
     */
    async function stopGridTrading() {
        console.log('[WEEX Bot] 停止网格交易...');
        
        try {
            for (const order of globalState.gridTrading.orders) {
                try {
                    await cancelOrder(order.symbol, order.orderId);
                    console.log(`[WEEX Bot] 已撤销订单: ${order.orderId}`);
                } catch (error) {
                    console.error(`[WEEX Bot] 撤销订单失败: ${order.orderId}`, error);
                }
            }

            globalState.gridTrading.isRunning = false;
            globalState.gridTrading.orders = [];
            
            return { success: true, message: '网格交易已停止' };
        } catch (error) {
            console.error('[WEEX Bot] 停止网格交易失败:', error);
            return { error: error.message };
        }
    }

    /**
     * 延迟函数
     */
    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // ============================================================
    // WebSocket 控制服务器
    // ============================================================

    /**
     * 连接到 WebSocket 服务器
     */
    function connectWebSocket() {
        console.log('[WEEX Bot] 尝试连接 WebSocket...');
        
        try {
            const ws = new WebSocket(CONFIG.controlServerUrl);

            ws.onopen = function() {
                console.log('[WEEX Bot] WebSocket 已连接');
                globalState.isConnected = true;
                globalState.wsConnection = ws;
                sendWebSocketMessage({
                    type: 'connected',
                    message: 'WEEX Bot 已连接',
                    timestamp: Date.now(),
                });
            };

            ws.onmessage = function(event) {
                console.log('[WEEX Bot] 收到消息:', event.data);
                handleWebSocketMessage(JSON.parse(event.data));
            };

            ws.onerror = function(error) {
                console.error('[WEEX Bot] WebSocket 错误:', error);
                globalState.isConnected = false;
            };

            ws.onclose = function() {
                console.log('[WEEX Bot] WebSocket 已断开');
                globalState.isConnected = false;
                // 5 秒后尝试重新连接
                setTimeout(connectWebSocket, 5000);
            };

        } catch (error) {
            console.error('[WEEX Bot] WebSocket 连接失败:', error);
            // 5 秒后尝试重新连接
            setTimeout(connectWebSocket, 5000);
        }
    }

    /**
     * 发送 WebSocket 消息
     */
    function sendWebSocketMessage(message) {
        if (globalState.wsConnection && globalState.wsConnection.readyState === WebSocket.OPEN) {
            globalState.wsConnection.send(JSON.stringify(message));
        }
    }

    /**
     * 处理 WebSocket 消息
     */
    async function handleWebSocketMessage(message) {
        console.log('[WEEX Bot] 处理命令:', message.command);

        let response = {
            id: message.id,
            timestamp: Date.now(),
        };

        try {
            switch (message.command) {
                case 'start_grid_trading':
                    response.result = await executeGridTrading(
                        message.symbol || CONFIG.defaultSymbol,
                        message.gridLevels || CONFIG.defaultGridLevels,
                        message.gridSpacing || CONFIG.defaultGridSpacing
                    );
                    break;

                case 'stop_grid_trading':
                    response.result = await stopGridTrading();
                    break;

                case 'get_account_info':
                    response.result = await getAccountInfo();
                    break;

                case 'get_ticker':
                    response.result = await getTicker(message.symbol || CONFIG.defaultSymbol);
                    break;

                case 'place_order':
                    response.result = await placeOrder(
                        message.symbol,
                        message.size,
                        message.type,
                        message.price,
                        message.orderType,
                        message.matchPrice
                    );
                    break;

                case 'cancel_order':
                    response.result = await cancelOrder(message.symbol, message.orderId);
                    break;

                case 'get_status':
                    response.result = {
                        isConnected: globalState.isConnected,
                        gridTrading: globalState.gridTrading,
                        stats: globalState.stats,
                    };
                    break;

                default:
                    response.error = `未知命令: ${message.command}`;
            }
        } catch (error) {
            response.error = error.message;
        }

        sendWebSocketMessage(response);
    }

    // ============================================================
    // HTTP 控制服务器
    // ============================================================

    /**
     * 通过 HTTP 处理命令
     */
    async function handleHttpCommand(command, params) {
        console.log('[WEEX Bot] 处理 HTTP 命令:', command);

        try {
            switch (command) {
                case 'start_grid_trading':
                    return await executeGridTrading(
                        params.symbol || CONFIG.defaultSymbol,
                        params.gridLevels || CONFIG.defaultGridLevels,
                        params.gridSpacing || CONFIG.defaultGridSpacing
                    );

                case 'stop_grid_trading':
                    return await stopGridTrading();

                case 'get_account_info':
                    return await getAccountInfo();

                case 'get_ticker':
                    return await getTicker(params.symbol || CONFIG.defaultSymbol);

                case 'place_order':
                    return await placeOrder(
                        params.symbol,
                        params.size,
                        params.type,
                        params.price,
                        params.orderType,
                        params.matchPrice
                    );

                case 'cancel_order':
                    return await cancelOrder(params.symbol, params.orderId);

                case 'get_status':
                    return {
                        isConnected: globalState.isConnected,
                        gridTrading: globalState.gridTrading,
                        stats: globalState.stats,
                    };

                default:
                    return { error: `未知命令: ${command}` };
            }
        } catch (error) {
            return { error: error.message };
        }
    }

    // ============================================================
    // 暴露到全局作用域
    // ============================================================
    window.WEEXBot = {
        // API 函数
        getAccountInfo,
        getTicker,
        placeOrder,
        cancelOrder,
        executeGridTrading,
        stopGridTrading,
        
        // 控制函数
        connectWebSocket,
        sendWebSocketMessage,
        handleHttpCommand,
        
        // 状态访问
        getState: () => globalState,
        getStats: () => globalState.stats,
        getGridStatus: () => globalState.gridTrading,
        
        // 配置访问
        getConfig: () => CONFIG,
        setConfig: (newConfig) => Object.assign(CONFIG, newConfig),
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
            width: 450px;
            background: #1a1a1a;
            border: 2px solid #00ff00;
            border-radius: 8px;
            padding: 20px;
            font-family: monospace;
            color: #00ff00;
            z-index: 10000;
            box-shadow: 0 0 20px rgba(0, 255, 0, 0.3);
            max-height: 600px;
            overflow-y: auto;
        `;

        panel.innerHTML = `
            <div style="margin-bottom: 10px; font-weight: bold; font-size: 14px;">
                🤖 WEEX Trading Bot v2.0
            </div>
            
            <div style="margin-bottom: 10px; font-size: 11px; color: #888;">
                状态: <span id="status-indicator" style="color: #ff0000;">未连接</span>
            </div>
            
            <div style="margin-bottom: 10px; font-size: 12px;">
                <button id="btn-connect" style="
                    background: #00ff00;
                    color: #000;
                    border: none;
                    padding: 8px 12px;
                    margin: 5px 5px 5px 0;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: bold;
                ">连接服务器</button>
                
                <button id="btn-start-grid" style="
                    background: #00ff00;
                    color: #000;
                    border: none;
                    padding: 8px 12px;
                    margin: 5px 5px 5px 0;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: bold;
                ">启动网格</button>
                
                <button id="btn-stop-grid" style="
                    background: #ff6600;
                    color: #000;
                    border: none;
                    padding: 8px 12px;
                    margin: 5px 5px 5px 0;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: bold;
                ">停止网格</button>
            </div>
            
            <div style="margin-bottom: 10px; font-size: 11px;">
                <div>订单统计:</div>
                <div>  总计: <span id="stat-total">0</span></div>
                <div>  成功: <span id="stat-success">0</span></div>
                <div>  失败: <span id="stat-failed">0</span></div>
            </div>
            
            <div id="bot-output" style="
                background: #000;
                border: 1px solid #00ff00;
                padding: 10px;
                height: 200px;
                overflow-y: auto;
                font-size: 10px;
                margin-top: 10px;
            "></div>
            
            <div style="margin-top: 10px; font-size: 10px; color: #888;">
                使用: window.WEEXBot.connectWebSocket()
            </div>
        `;

        document.body.appendChild(panel);

        // 事件监听
        document.getElementById('btn-connect').addEventListener('click', () => {
            appendOutput('连接到 WebSocket 服务器...');
            connectWebSocket();
        });

        document.getElementById('btn-start-grid').addEventListener('click', async () => {
            appendOutput('启动网格交易...');
            const result = await executeGridTrading(
                CONFIG.defaultSymbol,
                CONFIG.defaultGridLevels,
                CONFIG.defaultGridSpacing
            );
            appendOutput('结果: ' + JSON.stringify(result).substring(0, 100));
        });

        document.getElementById('btn-stop-grid').addEventListener('click', async () => {
            appendOutput('停止网格交易...');
            const result = await stopGridTrading();
            appendOutput('结果: ' + JSON.stringify(result).substring(0, 100));
        });

        // 定期更新统计信息
        setInterval(() => {
            document.getElementById('stat-total').textContent = globalState.stats.totalOrders;
            document.getElementById('stat-success').textContent = globalState.stats.successfulOrders;
            document.getElementById('stat-failed').textContent = globalState.stats.failedOrders;
            
            const indicator = document.getElementById('status-indicator');
            if (globalState.isConnected) {
                indicator.textContent = '已连接';
                indicator.style.color = '#00ff00';
            } else {
                indicator.textContent = '未连接';
                indicator.style.color = '#ff0000';
            }
        }, 1000);
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

    console.log('[WEEX Bot] v2.0 脚本已加载');
    console.log('[WEEX Bot] 使用方法: window.WEEXBot.connectWebSocket()');
    console.log('[WEEX Bot] 或者: window.WEEXBot.handleHttpCommand("start_grid_trading", {...})');

})();
