// ==UserScript==
// @name         WEEX 统一交易机器人 v4.0
// @namespace    http://tampermonkey.net/
// @version      4.0.2
// @description  WEEX 永续合约交易自动化脚本，支持市价/限价下单、账户查询、撤单、平仓和K线读取
// @author       Manus AI
// @match        https://www.weex.com/*
// @match        https://*.weex.com/*
// @grant        unsafeWindow
// @grant        GM_info
// @run-at       document-start
// ==/UserScript==

(function () {
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

    // 专门用于点击 Radix UI 组件（如标签页）
    function clickRadixElement(element) {
        if (!element) {
            throw new Error('元素不存在');
        }
        // Radix UI 组件需要 focus + Enter 键盘事件来触发
        element.focus();
        element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
        element.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
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
                availableBalance: null,
                unrealizedPnl: null,
                position: null,
                positions: [],
                timestamp: new Date().toISOString()
            };

            // 直接使用 querySelectorAll 遍历页面元素获取数据
            // 1. 获取可用余额 - 查找包含"可用"文字的元素
            const allElements = document.querySelectorAll('span, div, p');
            for (const el of allElements) {
                const text = el.textContent.trim();
                
                // 匹配"可用: 1,234.56" 或 "可用余额: 1234.56" 格式
                if (text.includes('可用') && !text.includes('不可用')) {
                    const match = text.match(/可用[：:\s]*([0-9,]+\.?\d*)/);
                    if (match) {
                        account.availableBalance = match[1].replace(/,/g, '');
                        log(`找到可用余额: ${account.availableBalance}`, 'info');
                        break;
                    }
                }
            }

            // 2. 获取权益/总余额
            for (const el of allElements) {
                const text = el.textContent.trim();
                if ((text.includes('权益') || text.includes('总余额') || text.includes('账户余额')) 
                    && !text.includes('可用')) {
                    const match = text.match(/([0-9,]+\.?\d*)/);
                    if (match) {
                        account.equity = match[1].replace(/,/g, '');
                        log(`找到权益: ${account.equity}`, 'info');
                        break;
                    }
                }
            }

            // 3. 获取未实现盈亏
            for (const el of allElements) {
                const text = el.textContent.trim();
                if (text.includes('未实现') || text.includes('浮动盈亏')) {
                    const match = text.match(/(-?[0-9,]+\.?\d*)/);
                    if (match) {
                        account.unrealizedPnl = match[1].replace(/,/g, '');
                        log(`找到未实现盈亏: ${account.unrealizedPnl}`, 'info');
                        break;
                    }
                }
            }

            // 4. 获取持仓信息 - WEEX 表格解析
            // WEEX 使用标准 table 结构
            // 列索引映射：
            // [0] 合约 - 包含币对名称、方向(多/空)、杠杆倍数
            // [1] 数量 - 张数（如 "89,490 张"）
            // [2] 开仓均价
            // [3] 标记价格
            // [4] 预估强平价
            // [5] 保证金比率
            // [6] 保证金
            // [7] 未实现盈亏
            // [8] 已实现盈亏
            
            let foundPositions = false;
            
            // 清理数字字符串的辅助函数
            const cleanNumber = (str) => {
                if (!str) return '0';
                return str.replace(/[^0-9.\-]/g, '') || '0';
            };
            
            // 查找持仓表格的 tbody
            const positionTable = document.querySelector('table[data-slot="table"] tbody[data-slot="table-body"]');
            if (positionTable) {
                const rows = positionTable.querySelectorAll('tr[data-slot="table-row"]');
                
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td[data-slot="table-cell"]');
                    if (cells.length >= 9) {
                        // 解析合约名称和方向
                        const contractCell = cells[0];
                        const symbolText = contractCell.querySelector('.text-text-primary')?.textContent?.trim() || '';
                        const sideElement = contractCell.querySelector('.text-xs.mr-1.px-1');
                        const sideText = sideElement?.textContent?.trim() || '';
                        const leverageText = contractCell.querySelector('.text-xs.ml-1.px-1')?.textContent?.trim() || '';
                        
                        // 完整合约名称（如 "BTC/USDT多200x"）
                        const fullSymbol = `${symbolText}${sideText}${leverageText}`;
                        
                        // 解析方向
                        let side = '';
                        if (sideText.includes('多')) {
                            side = 'long';
                        } else if (sideText.includes('空')) {
                            side = 'short';
                        }
                        
                        // 解析张数
                        const sizeText = cells[1]?.textContent?.trim() || '';
                        const sizeMatch = sizeText.match(/([0-9,]+)\s*张/);
                        const contracts = sizeMatch ? parseFloat(sizeMatch[1].replace(/,/g, '')) : 0;
                        
                        // 解析开仓均价
                        const entryPriceText = cells[2]?.textContent?.trim() || '';
                        const entryPrice = parseFloat(cleanNumber(entryPriceText)) || 0;
                        
                        // 解析未实现盈亏（从第8列提取，格式如 "-1,837.2297 USDT"）
                        const unrealizedPnlCell = cells[7];
                        const unrealizedPnlText = unrealizedPnlCell?.querySelector('p[dir="ltr"]')?.textContent?.trim() || '';
                        const unrealizedPnl = cleanNumber(unrealizedPnlText);
                        
                        // 计算 BTC 数量：张数 * 合约面值
                        // WEEX BTC 合约面值是 0.0001 BTC/张
                        const contractMultiplier = 0.0001;
                        const quantityInBTC = contracts * contractMultiplier;
                        
                        const position = {
                            symbol: fullSymbol,
                            side: side,
                            contracts: contracts,
                            quantity: quantityInBTC.toFixed(6),
                            size: quantityInBTC.toFixed(6),
                            entryPrice: entryPrice.toString(),
                            pnl: unrealizedPnl,
                            unrealizedPnl: unrealizedPnl
                        };
                        
                        // 验证是否是有效的持仓数据
                        if (position.symbol && contracts > 0 && side) {
                            account.positions.push(position);
                            if (!account.position) {
                                account.position = position;
                            }
                            foundPositions = true;
                            log(`解析到持仓: ${position.symbol} 方向=${side} 张数=${contracts} BTC=${position.size} 均价=${entryPrice} 盈亏=${unrealizedPnl}`, 'info');
                        }
                    }
                });
            }

            // 5. 如果没找到余额，尝试原始选择器
            if (!account.availableBalance) {
                const availableEl = document.querySelector('[class*="available"], [class*="free"]');
                if (availableEl) {
                    const match = availableEl.textContent.match(/([0-9,]+\.?\d*)/);
                    if (match) {
                        account.availableBalance = match[1].replace(/,/g, '');
                    }
                }
            }

            state.positions = account.positions;
            log(`账户状态获取成功: 可用余额 ${account.availableBalance || '未知'}, 持仓数 ${account.positions.length}`, 'success');
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
            // 1. 先切换到"当前委托"标签 - 使用 data-test-id
            let entrustTab = document.querySelector('[data-test-id="ContractPosition-trade-tab-entrust-current"]');
            
            if (entrustTab) {
                log('找到"当前委托"标签，正在切换...', 'info');
                // 使用 Radix UI 专用点击方法（focus + Enter）
                clickRadixElement(entrustTab);
                await sleep(1500);  // 增加等待时间让订单列表加载
                
                // 验证切换是否成功
                const isActive = entrustTab.getAttribute('data-state') === 'active';
                log(`标签切换${isActive ? '成功' : '失败'}, data-state=${entrustTab.getAttribute('data-state')}`, isActive ? 'success' : 'warn');
            } else {
                // 备用方案：通过文本查找
                const tabs = document.querySelectorAll('button[role="tab"]');
                for (const tab of tabs) {
                    if (tab.textContent.includes('当前委托')) {
                        log('通过文本找到"当前委托"标签', 'info');
                        clickRadixElement(tab);
                        await sleep(1500);
                        break;
                    }
                }
            }

            // 2. 等待订单列表加载并检查撤销按钮状态（最多等待5秒）
            let cancelButton = null;
            let buttonEnabled = false;
            
            for (let attempt = 0; attempt < 10; attempt++) {
                cancelButton = document.querySelector('[data-test-id="ContractPosition-all-cancel"]');
                
                if (cancelButton) {
                    buttonEnabled = !cancelButton.disabled && !cancelButton.hasAttribute('disabled');
                    log(`第${attempt+1}次检查: 按钮存在=${!!cancelButton}, 已启用=${buttonEnabled}`, 'info');
                    
                    if (buttonEnabled) {
                        log('撤销按钮已启用，准备点击', 'success');
                        break;
                    }
                }
                
                // 尝试滚动订单列表区域触发加载
                if (attempt === 2) {
                    const orderList = document.querySelector('[class*="order-list"], [class*="entrust"], [class*="scroll"]');
                    if (orderList) {
                        orderList.scrollTop = 0;
                        log('尝试滚动订单列表触发加载', 'info');
                    }
                }
                
                await sleep(500);
            }
            
            // 3. 如果按钮禁用，尝试查找单个订单的撤销按钮
            if (cancelButton && !buttonEnabled) {
                log('全部撤销按钮被禁用，尝试逐个撤销订单...', 'warn');
                
                // 查找订单行中的撤销按钮
                const orderRows = document.querySelectorAll('[class*="order-row"], [class*="entrust-item"], tr[class*="row"]');
                let cancelledCount = 0;
                
                for (const row of orderRows) {
                    const rowCancelBtn = row.querySelector('button');
                    if (rowCancelBtn && (rowCancelBtn.textContent.includes('撤销') || rowCancelBtn.textContent.includes('撤单'))) {
                        clickElement(rowCancelBtn);
                        await sleep(300);
                        
                        // 处理确认弹窗
                        const confirmBtn = document.querySelector('[class*="confirm"], button:not([disabled])');
                        if (confirmBtn && (confirmBtn.textContent.includes('确定') || confirmBtn.textContent.includes('确认'))) {
                            clickElement(confirmBtn);
                            await sleep(200);
                        }
                        
                        cancelledCount++;
                        log(`已撤销第 ${cancelledCount} 个订单`, 'info');
                    }
                }
                
                if (cancelledCount > 0) {
                    state.stats.cancelled += cancelledCount;
                    log(`已逐个撤销 ${cancelledCount} 个订单`, 'success');
                    return { success: true, message: `已撤销 ${cancelledCount} 个订单` };
                }
                
                // 如果没找到单个撤销按钮，说明确实没有订单
                log('未找到可撤销的订单（按钮禁用且无订单行）', 'warn');
                return { success: true, message: '无订单需要撤销（按钮禁用）' };
            }
            
            // 4. 点击全部撤销按钮
            if (cancelButton && buttonEnabled) {
                clickElement(cancelButton);
                log('已点击撤销按钮，等待确认弹窗...', 'info');
                await sleep(800);

                // 5. 查找确认按钮（弹窗中）
                const confirmButtons = document.querySelectorAll('button');
                for (const btn of confirmButtons) {
                    const text = btn.textContent.trim();
                    if (text === '确定' || text === '确认' || text === '是' || 
                        text === 'OK' || text === 'Confirm') {
                        const rect = btn.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            clickElement(btn);
                            log(`点击确认按钮: "${text}"`, 'info');
                            await sleep(500);
                            break;
                        }
                    }
                }

                state.stats.cancelled++;
                log('已执行一键撤销所有订单', 'success');
                return { success: true, message: '已执行一键撤销' };
            }

            // 6. 如果没有撤销按钮，可能没有订单
            log('未找到撤销按钮，可能没有待撤销的订单', 'warn');
            return { success: true, message: '无订单需要撤销' };
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
            version: '4.0.2',
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
    window.addEventListener('message', async function (event) {
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
        log('WEEX 统一交易机器人已加载 (v4.0.2)', 'success');
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
