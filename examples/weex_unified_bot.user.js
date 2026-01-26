// ==UserScript==
// @name         WEEX 统一交易机器人 v4.0
// @namespace    http://tampermonkey.net/
// @version      4.0.1
// @description  WEEX 永续合约交易自动化脚本，支持市价/限价下单、账户查询、撤单、平仓和K线读取
// @author       Manus AI
// @match        https://www.weex.com/*
// @match        https://*.weex.com/*
// @grant        unsafeWindow
// @grant        GM_info
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    // ===================================================================
    // 1. 配置区域 (CONFIG)
    // ===================================================================
    const CONFIG = {
        orderQuantity: 20,       // 每单数量（张）
        orderDelay: 800,         // 下单延迟（毫秒）
        debug: true,             // 调试模式
        wsServerUrl: 'ws://localhost:8765'  // WebSocket服务器地址
    };

    // ===================================================================
    // 2. DOM选择器 (SELECTORS)
    // ===================================================================
    const SELECTORS = {
        // 订单类型标签
        orderTypeTabs: '.order-type-tabs, [class*="orderType"]',
        limitTab: '[data-type="limit"], [class*="limit"]',
        marketTab: '[data-type="market"], [class*="market"]',

        // 输入框
        priceInput: 'input[class*="price"], input[placeholder*="价格"]',
        quantityInput: 'input[class*="amount"], input[class*="quantity"], input[placeholder*="数量"]',

        // 买卖按钮
        buyButton: 'button[class*="buy"], button[class*="long"]',
        sellButton: 'button[class*="sell"], button[class*="short"]',

        // 撤单按钮
        cancelAllButton: 'button:contains("一键撤销"), [class*="cancelAll"]',
        confirmButton: 'button:contains("确定"), button:contains("确认"), [class*="confirm"]',

        // 订单和持仓列表
        orderRow: 'div[role="row"]:not([header="true"]), tr:not(:first-child)',
        positionRow: '[class*="position-row"], [class*="positionItem"]',

        // K线相关
        klineContainer: '[class*="kline"], [class*="chart"]',
        currentPrice: '[class*="lastPrice"], [class*="current-price"], [id*="price"]',

        // 账户信息
        equityValue: '[class*="equity"], [class*="totalAssets"]',
        availableValue: '[class*="available"], [class*="availableBalance"]',
        unrealizedPnl: '[class*="unrealized"], [class*="pnl"]'
    };

    // ===================================================================
    // 3. 状态管理 (STATE)
    // ===================================================================
    const state = {
        isRunning: false,
        wsConnection: null,
        currentPrice: 0,
        orders: [],
        positions: [],
        stats: {
            totalPlaced: 0,
            buyPlaced: 0,
            sellPlaced: 0,
            cancelled: 0,
            failed: 0,
            startTime: null
        },
        logs: []
    };

    function resetState() {
        state.isRunning = false;
        state.currentPrice = 0;
        state.orders = [];
        state.positions = [];
        state.stats = {
            totalPlaced: 0, buyPlaced: 0, sellPlaced: 0, cancelled: 0, failed: 0,
            startTime: null
        };
        state.logs = [];
        log('状态已重置', 'info');
    }

    // ===================================================================
    // 4. 核心工具函数 (CORE UTILITIES)
    // ===================================================================

    function log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = `[${timestamp}] [${type.toUpperCase()}] ${message}`;
        if (CONFIG.debug) {
            const styles = {
                info: 'color: #2196F3',
                success: 'color: #4CAF50; font-weight: bold',
                error: 'color: #f44336; font-weight: bold;',
                warn: 'color: #ff9800'
            };
            console.log(`%c[WEEX Bot] ${logEntry}`, styles[type] || styles.info);
        }
        state.logs.push({ timestamp, type, message });
        // 保持日志数量在合理范围
        if (state.logs.length > 200) {
            state.logs = state.logs.slice(-100);
        }
    }

    function getElement(selector, context = document) {
        // 支持多个选择器，用逗号分隔
        const selectors = selector.split(',').map(s => s.trim());
        for (const sel of selectors) {
            try {
                // 处理 :contains 伪选择器
                if (sel.includes(':contains(')) {
                    const match = sel.match(/(.+):contains\("(.+)"\)/);
                    if (match) {
                        const baseSelector = match[1];
                        const text = match[2];
                        const elements = context.querySelectorAll(baseSelector);
                        for (const el of elements) {
                            if (el.textContent.includes(text)) {
                                return el;
                            }
                        }
                    }
                } else {
                    const el = context.querySelector(sel);
                    if (el) return el;
                }
            } catch (e) {
                // 忽略无效选择器
            }
        }
        return null;
    }

    function getElements(selector, context = document) {
        const results = [];
        const selectors = selector.split(',').map(s => s.trim());
        for (const sel of selectors) {
            try {
                if (sel.includes(':contains(')) {
                    const match = sel.match(/(.+):contains\("(.+)"\)/);
                    if (match) {
                        const baseSelector = match[1];
                        const text = match[2];
                        const elements = context.querySelectorAll(baseSelector);
                        for (const el of elements) {
                            if (el.textContent.includes(text)) {
                                results.push(el);
                            }
                        }
                    }
                } else {
                    const els = context.querySelectorAll(sel);
                    results.push(...els);
                }
            } catch (e) {
                // 忽略无效选择器
            }
        }
        return results;
    }

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function setInputValue(input, value) {
        if (!input) {
            throw new Error('输入框元素不存在');
        }
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        input.dispatchEvent(new Event('blur', { bubbles: true }));
    }

    function clickElement(element) {
        if (!element) {
            throw new Error('按钮元素不存在');
        }
        element.click();
        element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    }

    // ===================================================================
    // 5. 市场数据功能 (MARKET DATA)
    // ===================================================================

    async function getCurrentPrice() {
        log('正在获取当前价格...', 'info');
        try {
            // 尝试多种选择器获取当前价格
            const priceSelectors = [
                '[id*="bid-contract-0-price"]',
                '[class*="lastPrice"]',
                '[class*="current-price"]',
                '[class*="markPrice"]',
                '.price-value',
                '[data-price]'
            ];

            for (const selector of priceSelectors) {
                const el = document.querySelector(selector);
                if (el) {
                    const priceText = el.textContent.replace(/,/g, '').trim();
                    const price = parseFloat(priceText);
                    if (!isNaN(price) && price > 0) {
                        state.currentPrice = price;
                        log(`当前价格: ${price} USDT`, 'success');
                        return { success: true, price: price };
                    }
                }
            }

            throw new Error('无法获取当前价格');
        } catch (e) {
            log(`获取当前价格失败: ${e.message}`, 'error');
            return { success: false, error: e.message };
        }
    }

    async function getKlineData() {
        log('正在获取K线数据...', 'info');
        try {
            // 获取当前价格作为K线数据的一部分
            const priceResult = await getCurrentPrice();

            // 尝试从页面获取更多K线相关信息
            const klineInfo = {
                currentPrice: priceResult.success ? priceResult.price : null,
                high24h: null,
                low24h: null,
                volume24h: null,
                change24h: null,
                timestamp: new Date().toISOString()
            };

            // 尝试获取24小时高低价
            const highEl = document.querySelector('[class*="high"], [class*="24hHigh"]');
            const lowEl = document.querySelector('[class*="low"], [class*="24hLow"]');
            const volumeEl = document.querySelector('[class*="volume"], [class*="24hVol"]');
            const changeEl = document.querySelector('[class*="change"], [class*="priceChange"]');

            if (highEl) klineInfo.high24h = parseFloat(highEl.textContent.replace(/,/g, ''));
            if (lowEl) klineInfo.low24h = parseFloat(lowEl.textContent.replace(/,/g, ''));
            if (volumeEl) klineInfo.volume24h = volumeEl.textContent.trim();
            if (changeEl) klineInfo.change24h = changeEl.textContent.trim();

            log(`K线数据获取成功: 当前价格 ${klineInfo.currentPrice}`, 'success');
            return { success: true, data: klineInfo };
        } catch (e) {
            log(`获取K线数据失败: ${e.message}`, 'error');
            return { success: false, error: e.message };
        }
    }

    // ===================================================================
    // 6. 账户信息功能 (ACCOUNT INFO)
    // ===================================================================

    async function getAccountStatus() {
        log('正在获取账户状态...', 'info');
        try {
            const account = {
                equity: null,
                available: null,
                unrealizedPnl: null,
                positions: [],
                timestamp: new Date().toISOString()
            };

            // 获取账户基本信息
            const equityEl = getElement(SELECTORS.equityValue);
            const availableEl = getElement(SELECTORS.availableValue);
            const pnlEl = getElement(SELECTORS.unrealizedPnl);

            if (equityEl) account.equity = equityEl.textContent.trim();
            if (availableEl) account.available = availableEl.textContent.trim();
            if (pnlEl) account.unrealizedPnl = pnlEl.textContent.trim();

            // 获取持仓信息
            const positionRows = getElements(SELECTORS.positionRow);
            positionRows.forEach(row => {
                const cells = row.querySelectorAll('td, div[role="gridcell"], [class*="cell"]');
                if (cells.length >= 4) {
                    account.positions.push({
                        symbol: cells[0]?.textContent?.trim() || '',
                        side: cells[1]?.textContent?.trim() || '',
                        quantity: cells[2]?.textContent?.trim() || '',
                        entryPrice: cells[3]?.textContent?.trim() || '',
                        pnl: cells[4]?.textContent?.trim() || ''
                    });
                }
            });

            state.positions = account.positions;
            log(`账户状态获取成功: 可用余额 ${account.available}`, 'success');
            return { success: true, data: account };
        } catch (e) {
            log(`获取账户状态失败: ${e.message}`, 'error');
            return { success: false, error: e.message };
        }
    }

    // ===================================================================
    // 7. 订单管理功能 (ORDER MANAGEMENT)
    // ===================================================================

    async function getOpenOrders() {
        log('正在获取当前委托...', 'info');
        try {
            const orders = [];
            const rows = getElements(SELECTORS.orderRow);

            rows.forEach((row, index) => {
                const cells = row.querySelectorAll('td, div[role="gridcell"], [class*="cell"]');
                if (cells.length >= 5) {
                    orders.push({
                        id: index,
                        time: cells[0]?.textContent?.trim() || '',
                        symbol: cells[1]?.textContent?.trim() || '',
                        side: cells[2]?.textContent?.trim() || '',
                        type: cells[3]?.textContent?.trim() || '',
                        price: cells[4]?.textContent?.trim() || '',
                        quantity: cells[5]?.textContent?.trim() || '',
                        status: cells[6]?.textContent?.trim() || ''
                    });
                }
            });

            state.orders = orders;
            log(`获取到 ${orders.length} 个当前委托`, 'success');
            return { success: true, orders: orders };
        } catch (e) {
            log(`获取当前委托失败: ${e.message}`, 'error');
            return { success: false, error: e.message };
        }
    }

    async function cancelAllOrders() {
        log('准备一键撤销所有订单...', 'warn');
        try {
            // 查找一键撤销按钮
            const buttons = document.querySelectorAll('button, [role="button"]');
            let cancelButton = null;

            for (const btn of buttons) {
                if (btn.textContent.includes('一键撤销') || btn.textContent.includes('全部撤销')) {
                    cancelButton = btn;
                    break;
                }
            }

            if (cancelButton) {
                clickElement(cancelButton);
                await sleep(500);

                // 查找确认按钮
                const confirmButtons = document.querySelectorAll('button, [role="button"]');
                for (const btn of confirmButtons) {
                    if (btn.textContent.includes('确定') || btn.textContent.includes('确认')) {
                        clickElement(btn);
                        break;
                    }
                }

                state.stats.cancelled++;
                log('已执行一键撤销所有订单', 'success');
                return { success: true, message: '已执行一键撤销' };
            }

            throw new Error('未找到撤销按钮');
        } catch (e) {
            log(`撤销订单失败: ${e.message}`, 'error');
            return { success: false, error: e.message };
        }
    }

    async function cancelOrder(orderId) {
        log(`准备撤销订单: ${orderId}`, 'info');
        try {
            const rows = getElements(SELECTORS.orderRow);

            for (const row of rows) {
                // 在行内查找撤销按钮
                const cancelBtn = row.querySelector('button');
                if (cancelBtn && (cancelBtn.textContent.includes('撤销') || cancelBtn.textContent.includes('取消'))) {
                    clickElement(cancelBtn);
                    await sleep(300);

                    // 处理确认弹窗
                    const confirmButtons = document.querySelectorAll('button');
                    for (const btn of confirmButtons) {
                        if (btn.textContent.includes('确定') || btn.textContent.includes('确认')) {
                            clickElement(btn);
                            break;
                        }
                    }

                    state.stats.cancelled++;
                    log(`订单 ${orderId} 已撤销`, 'success');
                    return { success: true, orderId: orderId };
                }
            }

            throw new Error(`未找到订单 ${orderId}`);
        } catch (e) {
            log(`撤销订单失败: ${e.message}`, 'error');
            return { success: false, error: e.message };
        }
    }

    // ===================================================================
    // 8. 下单功能 (ORDER PLACEMENT)
    // ===================================================================

    async function placeOrder(options) {
        const { type = 'limit', side, quantity = CONFIG.orderQuantity, price } = options;
        log(`准备下单: ${type} ${side} ${quantity}张 @ ${price || '市价'}`, 'info');

        try {
            // 1. 选择订单类型（市价/限价）
            if (type === 'market') {
                const marketTab = document.querySelector('[class*="market"], [data-type="market"]');
                if (marketTab) {
                    clickElement(marketTab);
                    await sleep(200);
                }
            } else {
                const limitTab = document.querySelector('[class*="limit"], [data-type="limit"]');
                if (limitTab) {
                    clickElement(limitTab);
                    await sleep(200);
                }
            }

            // 2. 填写价格（限价单）
            if (type === 'limit' && price) {
                const priceInputs = document.querySelectorAll('input');
                for (const input of priceInputs) {
                    const placeholder = input.placeholder || '';
                    const className = input.className || '';
                    if (placeholder.includes('价格') || className.includes('price')) {
                        setInputValue(input, price.toString());
                        break;
                    }
                }
            }

            // 3. 填写数量
            const quantityInputs = document.querySelectorAll('input');
            for (const input of quantityInputs) {
                const placeholder = input.placeholder || '';
                const className = input.className || '';
                if (placeholder.includes('数量') || placeholder.includes('张') ||
                    className.includes('amount') || className.includes('quantity')) {
                    setInputValue(input, quantity.toString());
                    break;
                }
            }

            await sleep(100);

            // 4. 点击买入/卖出按钮
            const buttons = document.querySelectorAll('button');
            let targetButton = null;

            for (const btn of buttons) {
                const text = btn.textContent.toLowerCase();
                const className = (btn.className || '').toLowerCase();

                if (side === 'buy' || side === 'long') {
                    if (text.includes('买入') || text.includes('做多') ||
                        className.includes('buy') || className.includes('long')) {
                        targetButton = btn;
                        break;
                    }
                } else {
                    if (text.includes('卖出') || text.includes('做空') ||
                        className.includes('sell') || className.includes('short')) {
                        targetButton = btn;
                        break;
                    }
                }
            }

            if (targetButton) {
                clickElement(targetButton);
                await sleep(300);

                // 处理可能的确认弹窗
                const confirmButtons = document.querySelectorAll('button');
                for (const btn of confirmButtons) {
                    if (btn.textContent.includes('确定') || btn.textContent.includes('确认')) {
                        clickElement(btn);
                        break;
                    }
                }

                // 更新统计
                state.stats.totalPlaced++;
                if (side === 'buy' || side === 'long') {
                    state.stats.buyPlaced++;
                } else {
                    state.stats.sellPlaced++;
                }

                log(`下单成功: ${type} ${side} ${quantity}张 @ ${price || '市价'}`, 'success');
                return { success: true, type, side, quantity, price };
            }

            throw new Error('未找到下单按钮');
        } catch (e) {
            state.stats.failed++;
            log(`下单失败: ${e.message}`, 'error');
            return { success: false, error: e.message };
        }
    }

    // 便捷方法：限价买入
    async function placeLimitBuy(price, quantity = CONFIG.orderQuantity) {
        return await placeOrder({ type: 'limit', side: 'buy', price, quantity });
    }

    // 便捷方法：限价卖出
    async function placeLimitSell(price, quantity = CONFIG.orderQuantity) {
        return await placeOrder({ type: 'limit', side: 'sell', price, quantity });
    }

    // 便捷方法：市价买入
    async function placeMarketBuy(quantity = CONFIG.orderQuantity) {
        return await placeOrder({ type: 'market', side: 'buy', quantity });
    }

    // 便捷方法：市价卖出
    async function placeMarketSell(quantity = CONFIG.orderQuantity) {
        return await placeOrder({ type: 'market', side: 'sell', quantity });
    }

    // ===================================================================
    // 9. 平仓功能 (CLOSE POSITION)
    // ===================================================================

    async function closePosition(symbol, options = {}) {
        const { type = 'market' } = options;
        log(`准备平仓: ${symbol} (${type})`, 'info');

        try {
            // 查找持仓列表中的平仓按钮
            const rows = getElements(SELECTORS.positionRow);

            for (const row of rows) {
                const symbolCell = row.querySelector('[class*="symbol"], td:first-child');
                if (symbolCell && symbolCell.textContent.includes(symbol)) {
                    // 找到对应持仓，查找平仓按钮
                    const closeBtn = row.querySelector('button');
                    if (closeBtn && (closeBtn.textContent.includes('平仓') || closeBtn.textContent.includes('关闭'))) {
                        clickElement(closeBtn);
                        await sleep(500);

                        // 处理平仓弹窗
                        if (type === 'market') {
                            const marketBtn = document.querySelector('[class*="market"], button:contains("市价")');
                            if (marketBtn) clickElement(marketBtn);
                        }

                        // 确认平仓
                        await sleep(200);
                        const confirmButtons = document.querySelectorAll('button');
                        for (const btn of confirmButtons) {
                            if (btn.textContent.includes('确定') || btn.textContent.includes('确认')) {
                                clickElement(btn);
                                break;
                            }
                        }

                        log(`平仓成功: ${symbol}`, 'success');
                        return { success: true, symbol, type };
                    }
                }
            }

            throw new Error(`未找到 ${symbol} 的持仓`);
        } catch (e) {
            log(`平仓失败: ${e.message}`, 'error');
            return { success: false, error: e.message };
        }
    }

    // ===================================================================
    // 10. WebSocket 通信 (WEBSOCKET COMMUNICATION)
    // ===================================================================

    function connectWebSocket(url = CONFIG.wsServerUrl) {
        log(`正在连接WebSocket服务器: ${url}`, 'info');

        try {
            state.wsConnection = new WebSocket(url);

            state.wsConnection.onopen = () => {
                log('WebSocket连接成功', 'success');
                // 发送连接确认
                sendWsMessage({ type: 'connected', timestamp: new Date().toISOString() });
            };

            state.wsConnection.onmessage = async (event) => {
                try {
                    const message = JSON.parse(event.data);
                    log(`收到命令: ${message.action}`, 'info');
                    await handleWsCommand(message);
                } catch (e) {
                    log(`处理消息失败: ${e.message}`, 'error');
                }
            };

            state.wsConnection.onclose = () => {
                log('WebSocket连接已关闭', 'warn');
                state.wsConnection = null;
            };

            state.wsConnection.onerror = (error) => {
                log(`WebSocket错误: ${error.message || '未知错误'}`, 'error');
            };

            return { success: true, message: '正在连接...' };
        } catch (e) {
            log(`WebSocket连接失败: ${e.message}`, 'error');
            return { success: false, error: e.message };
        }
    }

    function sendWsMessage(message) {
        if (state.wsConnection && state.wsConnection.readyState === WebSocket.OPEN) {
            state.wsConnection.send(JSON.stringify(message));
        }
    }

    async function handleWsCommand(command) {
        const { id, action, params = {} } = command;
        log(`处理命令: ${action}, ID: ${id}`, 'info');
        let result;

        try {
            switch (action) {
                case 'get_price':
                    result = await getCurrentPrice();
                    break;
                case 'get_kline':
                    result = await getKlineData();
                    break;
                case 'get_account':
                    result = await getAccountStatus();
                    break;
                case 'get_orders':
                    result = await getOpenOrders();
                    break;
                case 'place_order':
                    result = await placeOrder(params);
                    break;
                case 'cancel_order':
                    result = await cancelOrder(params.orderId || params.order_id);
                    break;
                case 'cancel_all':
                    result = await cancelAllOrders();
                    break;
                case 'close_position':
                    result = await closePosition(params.symbol, params);
                    break;
                case 'get_stats':
                    result = getStats();
                    break;
                case 'switch_symbol':
                    result = await switchSymbol(params.symbol);
                    break;
                default:
                    result = { success: false, error: `未知命令: ${action}` };
            }
        } catch (e) {
            log(`命令执行失败: ${e.message}`, 'error');
            result = { success: false, error: e.message };
        }

        // 发送结果回服务器（包含请求ID以便后端匹配响应）
        sendWsMessage({ 
            type: 'response', 
            id: id,
            action, 
            result, 
            timestamp: new Date().toISOString() 
        });
    }

    // 切换交易对
    async function switchSymbol(symbol) {
        log(`切换交易对: ${symbol}`, 'info');
        try {
            // WEEX页面上的交易对通常通过URL切换
            // 例如: /futures/BTC-USDT -> /futures/ETH-USDT
            const currentUrl = window.location.href;
            const symbolFormatted = symbol.replace('USDT', '-USDT');
            
            if (currentUrl.includes('/futures/')) {
                const newUrl = currentUrl.replace(/\/futures\/[A-Z]+-USDT/, `/futures/${symbolFormatted}`);
                if (newUrl !== currentUrl) {
                    window.location.href = newUrl;
                    return { success: true, message: `已切换到 ${symbol}` };
                }
            }
            
            // 如果URL已经是目标交易对，直接返回成功
            return { success: true, message: `当前已在 ${symbol}` };
        } catch (e) {
            log(`切换交易对失败: ${e.message}`, 'error');
            return { success: false, error: e.message };
        }
    }

    // ===================================================================
    // 11. 统计和调试 (STATS & DEBUG)
    // ===================================================================

    function getStats() {
        return {
            ...state.stats,
            currentPrice: state.currentPrice,
            ordersCount: state.orders.length,
            positionsCount: state.positions.length,
            wsConnected: state.wsConnection?.readyState === WebSocket.OPEN,
            logs: state.logs.slice(-50)
        };
    }

    // ===================================================================
    // 12. 全局 API 暴露
    // ===================================================================
    const weexBotAPI = {
        // 市场数据
        getCurrentPrice,
        getKlineData,

        // 账户信息
        getAccountStatus,

        // 订单管理
        getOpenOrders,
        cancelOrder,
        cancelAllOrders,

        // 下单功能
        placeOrder,
        placeLimitBuy,
        placeLimitSell,
        placeMarketBuy,
        placeMarketSell,

        // 平仓功能
        closePosition,

        // 交易对切换
        switchSymbol,

        // WebSocket通信
        connect: connectWebSocket,
        disconnect: () => {
            if (state.wsConnection) {
                state.wsConnection.close();
                state.wsConnection = null;
            }
        },
        sendMessage: sendWsMessage,

        // 系统功能
        getStats,
        reset: resetState,
        config: CONFIG,
        state: state
    };

    // ===================================================================
    // 13. 暴露API到页面上下文 (关键修复)
    // ===================================================================
    
    // 方法1: 直接赋值给window
    window.weexBot = weexBotAPI;
    
    // 方法2: 使用unsafeWindow (Tampermonkey特有)
    if (typeof unsafeWindow !== 'undefined') {
        unsafeWindow.weexBot = weexBotAPI;
    }
    
    // 方法3: 通过script标签注入到页面上下文 (最可靠的方法)
    function injectToPageContext() {
        const apiString = JSON.stringify({
            version: '4.0.1',
            injected: true
        });
        
        const scriptContent = `
            (function() {
                // 创建一个临时对象来保存状态
                if (window.__weexBotReady) return;
                window.__weexBotReady = true;
                
                // 创建一个代理对象，用于与油猴脚本通信
                window.__weexBotProxy = {
                    pendingCalls: [],
                    call: function(method, args) {
                        return new Promise((resolve, reject) => {
                            const callId = Date.now() + '_' + Math.random();
                            this.pendingCalls.push({ id: callId, resolve, reject });
                            window.postMessage({ 
                                type: 'WEEX_BOT_CALL', 
                                method: method, 
                                args: args,
                                callId: callId
                            }, '*');
                            // 10秒超时
                            setTimeout(() => {
                                const idx = this.pendingCalls.findIndex(c => c.id === callId);
                                if (idx >= 0) {
                                    this.pendingCalls.splice(idx, 1);
                                    reject(new Error('Call timeout'));
                                }
                            }, 10000);
                        });
                    }
                };
                
                // 监听油猴脚本的响应
                window.addEventListener('message', function(event) {
                    if (event.data && event.data.type === 'WEEX_BOT_RESPONSE') {
                        const idx = window.__weexBotProxy.pendingCalls.findIndex(c => c.id === event.data.callId);
                        if (idx >= 0) {
                            const call = window.__weexBotProxy.pendingCalls.splice(idx, 1)[0];
                            if (event.data.error) {
                                call.reject(new Error(event.data.error));
                            } else {
                                call.resolve(event.data.result);
                            }
                        }
                    }
                });
                
                console.log('[WEEX Bot] 页面上下文代理已初始化');
            })();
        `;
        
        const script = document.createElement('script');
        script.textContent = scriptContent;
        (document.head || document.documentElement).appendChild(script);
        script.remove();
    }
    
    // 监听页面上下文的调用请求
    window.addEventListener('message', async function(event) {
        if (event.data && event.data.type === 'WEEX_BOT_CALL') {
            const { method, args, callId } = event.data;
            try {
                let result;
                if (weexBotAPI[method] && typeof weexBotAPI[method] === 'function') {
                    result = await weexBotAPI[method].apply(null, args || []);
                } else {
                    throw new Error(`Method ${method} not found`);
                }
                window.postMessage({ type: 'WEEX_BOT_RESPONSE', callId, result }, '*');
            } catch (e) {
                window.postMessage({ type: 'WEEX_BOT_RESPONSE', callId, error: e.message }, '*');
            }
        }
    });
    
    // 注入到页面上下文
    injectToPageContext();

    // 初始化
    resetState();
    state.stats.startTime = new Date().toISOString();

    // 延迟打印日志，确保页面加载完成
    const printWelcome = () => {
        log('========================================', 'info');
        log('WEEX 统一交易机器人已加载 (v4.0.1)', 'success');
        log('使用 weexBot 调用功能', 'info');
        log('========================================', 'info');
        log('可用命令:', 'info');
        log('  weexBot.getCurrentPrice()     - 获取当前价格', 'info');
        log('  weexBot.getKlineData()        - 获取K线数据', 'info');
        log('  weexBot.getAccountStatus()    - 获取账户状态', 'info');
        log('  weexBot.placeMarketBuy(20)    - 市价买入20张', 'info');
        log('  weexBot.placeMarketSell(20)   - 市价卖出20张', 'info');
        log('  weexBot.placeLimitBuy(87000, 20)  - 限价买入', 'info');
        log('  weexBot.placeLimitSell(88000, 20) - 限价卖出', 'info');
        log('  weexBot.cancelAllOrders()     - 一键撤销', 'info');
        log('  weexBot.closePosition("BTC")  - 平仓', 'info');
        log('  weexBot.connect()             - 连接后端', 'info');
        log('========================================', 'info');
        
        // 验证API是否成功暴露
        if (typeof window.weexBot !== 'undefined') {
            log('✅ weexBot API 已成功暴露到全局作用域', 'success');
        } else {
            log('⚠️ 如果控制台无法访问weexBot，请尝试刷新页面', 'warn');
        }
    };
    
    // 根据页面加载状态决定何时打印欢迎信息
    if (document.readyState === 'complete') {
        printWelcome();
    } else {
        window.addEventListener('load', printWelcome);
    }

})();
