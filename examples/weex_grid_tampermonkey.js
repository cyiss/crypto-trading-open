// ==UserScript==
// @name         WEEX 统一交易机器人
// @namespace    http://tampermonkey.net/
// @version      3.0.0
// @description  WEEX 永续合约交易自动化脚本，支持网格交易、账户查询和订单管理
// @author       Manus AI
// @match        https://www.weex.com/*
// @grant        unsafeWindow
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    // ===================================================================
    // 1. 配置区域 (CONFIG)
    // ===================================================================
    const CONFIG = {
        gridCount: 10,           // 网格数量（买卖各一半）
        gridSpacing: 500,        // 网格间距 (USDT)
        orderQuantity: 20,       // 每单数量（张）
        orderDelay: 800,         // 下单延迟（毫秒）
        debug: true              // 调试模式
    };

    // ===================================================================
    // 2. 状态管理 (STATE)
    // ===================================================================
    const state = {
        isRunning: false,
        currentPrice: 0,
        orders: { buy: [], sell: [] },
        stats: {},
        logs: []
    };

    function resetState() {
        state.isRunning = false;
        state.currentPrice = 0;
        state.orders = { buy: [], sell: [] };
        state.stats = {
            totalPlaced: 0, buyPlaced: 0, sellPlaced: 0, failed: 0,
            startTime: null, endTime: null
        };
        state.logs = [];
        log('状态已重置', 'info');
    }
    resetState(); // 初始化状态

    // ===================================================================
    // 3. 核心函数 (CORE FUNCTIONS)
    // ===================================================================

    // ------------------- 日志 -------------------
    function log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = `[${timestamp}] [${type.toUpperCase()}] ${message}`;
        if (CONFIG.debug) {
            const styles = {
                info: 'color: #2196F3', success: 'color: #4CAF50; font-weight: bold',
                error: 'color: #f44336; font-weight: bold;', warn: 'color: #ff9800'
            };
            console.log(`%c[WEEX Bot] ${logEntry}`, styles[type] || styles.info);
        }
        state.logs.push({ timestamp, type, message });
    }

    // ------------------- DOM 操作 -------------------
    function getElement(selector, context = document) { return context.querySelector(selector); }
    function getElements(selector, context = document) { return context.querySelectorAll(selector); }
    function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

    function setInputValue(input, value) {
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // ===================================================================
    // 4. 交易功能 (TRADING FUNCTIONS)
    // ===================================================================

    // ------------------- 账户信息 -------------------
    async function getAccountInfo() {
        log('正在获取账户信息...', 'info');
        try {
            const account = {
                equity: getElement('.equity-value')?.textContent || 'N/A',
                available: getElement('.available-value')?.textContent || 'N/A',
                unrealizedPNL: getElement('.unrealized-pnl-value')?.textContent || 'N/A',
                timestamp: new Date().toISOString()
            };
            log(`账户信息获取成功: 可用 ${account.available}`, 'success');
            return account;
        } catch (e) {
            log(`获取账户信息失败: ${e.message}`, 'error');
            return { error: e.message };
        }
    }

    // ------------------- 订单管理 -------------------
    async function getOpenOrders() {
        log('正在获取当前委托...', 'info');
        try {
            const orders = [];
            const rows = getElements('div[role="row"]:not([header="true"])'); // 适配WEEX的表格结构
            rows.forEach(row => {
                const cells = getElements('div[role="gridcell"]', row);
                if (cells.length > 8) {
                    orders.push({
                        time: cells[0]?.textContent || '',
                        symbol: cells[1]?.textContent || '',
                        direction: cells[2]?.textContent || '',
                        type: cells[3]?.textContent || '',
                        quantity: cells[5]?.textContent || '',
                        price: cells[7]?.textContent || '',
                        status: cells[9]?.textContent || ''
                    });
                }
            });
            log(`获取到 ${orders.length} 个当前委托`, 'success');
            return orders;
        } catch (e) {
            log(`获取当前委托失败: ${e.message}`, 'error');
            return { error: e.message };
        }
    }

    async function cancelAllOrders() {
        log('准备一键撤销所有订单...', 'warn');
        try {
            const cancelButton = Array.from(getElements('button')).find(b => b.textContent.includes('一键撤销'));
            if (cancelButton) {
                cancelButton.click();
                await sleep(500); // 等待确认弹窗
                const confirmButton = Array.from(getElements('button')).find(b => b.textContent.includes('确定'));
                if (confirmButton) {
                    confirmButton.click();
                    log('已执行一键撤销所有订单', 'success');
                    return { success: true, message: '已执行一键撤销' };
                }
            }
            throw new Error('未找到撤销按钮');
        } catch (e) {
            log(`撤销订单失败: ${e.message}`, 'error');
            return { error: e.message };
        }
    }

    // ------------------- 网格交易 -------------------
    async function placeOrder(price, quantity, isBuy) {
        return new Promise(async (resolve) => {
            try {
                const priceInput = getElement('input[id*="price"]');
                const amountInput = getElement('input[id*="amount"]');
                const button = isBuy ? getElement('button[class*="buy"]') : getElement('button[class*="sell"]');

                if (!priceInput || !amountInput || !button) {
                    throw new Error('找不到必要的下单DOM元素');
                }

                setInputValue(priceInput, price.toString());
                setInputValue(amountInput, quantity.toString());
                await sleep(100);
                button.click();

                const side = isBuy ? '买入' : '卖出';
                log(`${side} ${quantity}张 @ ${price} USDT`, 'success');
                state.stats[isBuy ? 'buyPlaced' : 'sellPlaced']++;
                state.stats.totalPlaced++;
                resolve(true);

            } catch (e) {
                log(`下单失败: ${e.message}`, 'error');
                state.stats.failed++;
                resolve(false);
            }
        });
    }

    async function executeGridTrading() {
        if (state.isRunning) {
            log('网格交易已在运行中', 'warn');
            return state.stats;
        }
        resetState();
        state.isRunning = true;
        state.stats.startTime = new Date().toISOString();

        log('===== 开始执行网格交易 =====', 'info');

        state.currentPrice = parseFloat(getElement('[id*="bid-contract-0-price"]')?.textContent.replace(/,/g, '')) || 87800;
        log(`当前价格: ${state.currentPrice} USDT`, 'info');

        const halfGrid = Math.floor(CONFIG.gridCount / 2);
        const buyPrices = Array.from({length: halfGrid}, (_, i) => Math.round(state.currentPrice - CONFIG.gridSpacing * (i + 1)));
        const sellPrices = Array.from({length: halfGrid}, (_, i) => Math.round(state.currentPrice + CONFIG.gridSpacing * (i + 1)));

        log(`买单价格: ${buyPrices.join(', ')}`, 'info');
        for (const price of buyPrices) {
            await placeOrder(price, CONFIG.orderQuantity, true);
            await sleep(CONFIG.orderDelay);
        }

        log(`卖单价格: ${sellPrices.join(', ')}`, 'info');
        for (const price of sellPrices) {
            await placeOrder(price, CONFIG.orderQuantity, false);
            await sleep(CONFIG.orderDelay);
        }

        state.stats.endTime = new Date().toISOString();
        state.isRunning = false;
        log('===== 网格交易执行完成 =====', 'success');
        return getStats();
    }

    // ===================================================================
    // 5. 全局 API 暴露
    // ===================================================================
    function getStats() {
        return { ...state.stats, logs: state.logs.slice(-50) };
    }

    window.weexBot = {
        // 网格交易
        startGrid: executeGridTrading,
        // 账户与订单
        getAccountInfo,
        getOpenOrders,
        cancelAllOrders,
        // 系统
        getStats,
        reset: resetState,
        config: CONFIG,
        state: state // 仅供调试
    };

    log('========================================', 'info');
    log('WEEX 统一交易机器人已加载 (v3.0.0)', 'success');
    log('使用 window.weexBot 调用功能', 'info');
    log('例如: weexBot.startGrid()', 'info');
    log('========================================', 'info');

})();
