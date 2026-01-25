// ==UserScript==
// @name         WEEX 网格交易机器人
// @namespace    http://tampermonkey.net/
// @version      2.0.0
// @description  WEEX 永续合约网格交易自动化脚本
// @author       Manus Trading Bot
// @match        https://www.weex.com/*
// @grant        unsafeWindow
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    // ==================== 配置区域 ====================
    const CONFIG = {
        // 网格配置
        gridCount: 10,           // 网格数量（买卖各一半）
        gridSpacing: 500,        // 网格间距 (USDT)
        orderQuantity: 20,       // 每单数量（张）
        
        // 下单延迟（毫秒）
        orderDelay: 800,
        
        // 调试模式
        debug: true
    };

    // ==================== 状态管理 ====================
    const state = {
        isRunning: false,
        currentPrice: 0,
        orders: {
            buy: [],
            sell: []
        },
        stats: {
            totalPlaced: 0,
            buyPlaced: 0,
            sellPlaced: 0,
            failed: 0,
            startTime: null,
            endTime: null
        },
        logs: []
    };

    // ==================== 日志函数 ====================
    function log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = `[${timestamp}] [${type.toUpperCase()}] ${message}`;
        
        if (CONFIG.debug) {
            const styles = {
                info: 'color: #2196F3',
                success: 'color: #4CAF50; font-weight: bold',
                error: 'color: #f44336; font-weight: bold',
                warn: 'color: #ff9800'
            };
            console.log(`%c[WEEX Grid] ${logEntry}`, styles[type] || styles.info);
        }
        
        state.logs.push({ timestamp, type, message });
    }

    // ==================== DOM 操作函数 ====================
    
    /**
     * 模拟用户输入（兼容React）
     */
    function setInputValue(input, value) {
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        nativeInputValueSetter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    /**
     * 获取价格输入框
     */
    function getPriceInput() {
        return document.getElementById('operation-input-price') ||
               document.querySelector('input[placeholder*="价格"]');
    }

    /**
     * 获取数量输入框
     */
    function getAmountInput() {
        return document.getElementById('operation-input-amount') ||
               document.querySelector('input[placeholder*="数量"]');
    }

    /**
     * 获取买入按钮
     */
    function getBuyButton() {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            if (btn.textContent.includes('买入开多')) {
                return btn;
            }
        }
        return null;
    }

    /**
     * 获取卖出按钮
     */
    function getSellButton() {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            if (btn.textContent.includes('卖出开空')) {
                return btn;
            }
        }
        return null;
    }

    /**
     * 获取当前价格
     */
    function getCurrentPrice() {
        // 尝试从页面获取当前价格
        const priceElements = document.querySelectorAll('[id^="bid-contract-0-price"], [id^="ask-contract-0-price"]');
        if (priceElements.length > 0) {
            const priceText = priceElements[0].textContent.replace(/,/g, '');
            return parseFloat(priceText);
        }
        
        // 备选方案：从标题获取
        const title = document.title;
        const match = title.match(/(\d+\.?\d*)/);
        if (match) {
            return parseFloat(match[1]);
        }
        
        return 0;
    }

    // ==================== 订单函数 ====================

    /**
     * 下单个订单
     */
    async function placeOrder(price, quantity, isBuy) {
        return new Promise((resolve) => {
            try {
                const priceInput = getPriceInput();
                const amountInput = getAmountInput();
                const orderButton = isBuy ? getBuyButton() : getSellButton();

                if (!priceInput || !amountInput || !orderButton) {
                    log(`找不到必要的DOM元素`, 'error');
                    resolve(false);
                    return;
                }

                // 设置价格
                setInputValue(priceInput, price.toString());
                
                // 设置数量
                setInputValue(amountInput, quantity.toString());

                // 等待UI更新后点击按钮
                setTimeout(() => {
                    orderButton.click();
                    
                    const side = isBuy ? '买入' : '卖出';
                    log(`${side} ${quantity}张 @ ${price} USDT`, 'success');
                    
                    // 记录订单
                    const orderRecord = {
                        price,
                        quantity,
                        side: isBuy ? 'buy' : 'sell',
                        time: new Date().toISOString(),
                        status: 'placed'
                    };
                    
                    if (isBuy) {
                        state.orders.buy.push(orderRecord);
                        state.stats.buyPlaced++;
                    } else {
                        state.orders.sell.push(orderRecord);
                        state.stats.sellPlaced++;
                    }
                    state.stats.totalPlaced++;
                    
                    resolve(true);
                }, 200);

            } catch (e) {
                log(`下单失败: ${e.message}`, 'error');
                state.stats.failed++;
                resolve(false);
            }
        });
    }

    /**
     * 计算网格价格
     */
    function calculateGridPrices(currentPrice) {
        const halfGrid = Math.floor(CONFIG.gridCount / 2);
        
        const buyPrices = [];
        const sellPrices = [];
        
        // 买入价格（低于当前价格）
        for (let i = 1; i <= halfGrid; i++) {
            const price = Math.round(currentPrice - CONFIG.gridSpacing * i);
            buyPrices.push(price);
        }
        
        // 卖出价格（高于当前价格）
        for (let i = 1; i <= halfGrid; i++) {
            const price = Math.round(currentPrice + CONFIG.gridSpacing * i);
            sellPrices.push(price);
        }
        
        return { buyPrices, sellPrices };
    }

    /**
     * 执行网格交易
     */
    async function executeGridTrading() {
        if (state.isRunning) {
            log('网格交易已在运行中', 'warn');
            return state.stats;
        }

        state.isRunning = true;
        state.stats.startTime = new Date().toISOString();
        
        log('========================================', 'info');
        log('开始执行网格交易', 'info');
        log('========================================', 'info');

        // 获取当前价格
        state.currentPrice = getCurrentPrice();
        if (state.currentPrice === 0) {
            state.currentPrice = 87868; // 默认价格
        }
        log(`当前价格: ${state.currentPrice} USDT`, 'info');

        // 计算网格价格
        const { buyPrices, sellPrices } = calculateGridPrices(state.currentPrice);
        
        log(`买入价格: ${buyPrices.join(', ')}`, 'info');
        log(`卖出价格: ${sellPrices.join(', ')}`, 'info');

        // 下买单
        log('----------------------------------------', 'info');
        log(`开始下买单 (共${buyPrices.length}个)`, 'info');
        log('----------------------------------------', 'info');
        
        for (const price of buyPrices) {
            await placeOrder(price, CONFIG.orderQuantity, true);
            await sleep(CONFIG.orderDelay);
        }

        // 下卖单
        log('----------------------------------------', 'info');
        log(`开始下卖单 (共${sellPrices.length}个)`, 'info');
        log('----------------------------------------', 'info');
        
        for (const price of sellPrices) {
            await placeOrder(price, CONFIG.orderQuantity, false);
            await sleep(CONFIG.orderDelay);
        }

        state.stats.endTime = new Date().toISOString();
        state.isRunning = false;

        // 打印统计
        log('========================================', 'info');
        log('网格交易执行完成', 'success');
        log('========================================', 'info');
        log(`总下单: ${state.stats.totalPlaced}`, 'info');
        log(`买单: ${state.stats.buyPlaced}`, 'info');
        log(`卖单: ${state.stats.sellPlaced}`, 'info');
        log(`失败: ${state.stats.failed}`, 'info');

        return getStats();
    }

    /**
     * 获取统计信息
     */
    function getStats() {
        return {
            ...state.stats,
            currentPrice: state.currentPrice,
            orders: state.orders,
            config: CONFIG,
            logs: state.logs.slice(-50) // 最近50条日志
        };
    }

    /**
     * 重置状态
     */
    function resetState() {
        state.isRunning = false;
        state.currentPrice = 0;
        state.orders = { buy: [], sell: [] };
        state.stats = {
            totalPlaced: 0,
            buyPlaced: 0,
            sellPlaced: 0,
            failed: 0,
            startTime: null,
            endTime: null
        };
        state.logs = [];
        log('状态已重置', 'info');
    }

    /**
     * 辅助函数：延迟
     */
    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // ==================== 暴露全局API ====================
    window.weexGrid = {
        start: executeGridTrading,
        getStats: getStats,
        reset: resetState,
        config: CONFIG,
        state: state
    };

    // ==================== 初始化 ====================
    log('========================================', 'info');
    log('WEEX 网格交易机器人已加载', 'success');
    log('========================================', 'info');
    log('使用方法:', 'info');
    log('  weexGrid.start()  - 开始网格交易', 'info');
    log('  weexGrid.getStats() - 获取统计信息', 'info');
    log('  weexGrid.reset() - 重置状态', 'info');
    log('========================================', 'info');

})();
