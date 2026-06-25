/* ============================================================
   app.js v3 — 小红书爆款雷达 前端主逻辑
   改进：SSE 流式反馈 + Toast 通知 + 防抖 + 进度提示
   ============================================================ */

// ===== 全局状态 =====
const state = {
    opportunities: [],
    activeCategory: null,
    isSearching: false,       // 防重复请求
    activeSSE: null,          // 当前 SSE 读取器（用于取消）
    activeLoadingTag: null,   // 当前 loading 的热词/快搜标签
};

// ===== DOM 引用 =====
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const rankingList = $('#ranking-list');
const categoryInput = $('#category-input');
const searchBtn = $('#search-btn');
const quickTags = $('#quick-tags');
const loadingEl = $('#loading-indicator');
const detailOverlay = $('#detail-overlay');
const detailContent = $('#detail-content');
const detailClose = $('#detail-close');
const totalBadge = $('#total-badge');
const suggestions = $('#category-suggestions');

// ===== Toast 通知系统 =====
function showToast(message, type) {
    if (!type) type = 'info';
    const container = document.getElementById('toast-container') || (function () {
        const div = document.createElement('div');
        div.id = 'toast-container';
        div.className = 'toast-container';
        document.body.appendChild(div);
        return div;
    })();
    var icons = { error: '✕', success: '✓', warning: '⚠', info: 'ℹ' };
    var toast = document.createElement('div');
    toast.className = 'toast-item toast-' + type;
    toast.innerHTML = '<span class="toast-icon">' + (icons[type] || '') + '</span><span>' + message + '</span>';
    container.appendChild(toast);
    setTimeout(function () {
        if (toast.parentNode) toast.remove();
    }, 5000);
}

// ===== 搜索锁（防重复请求）=====
function lockSearch() {
    state.isSearching = true;
    searchBtn.classList.add('loading');
    searchBtn.disabled = true;
}

function unlockSearch() {
    state.isSearching = false;
    searchBtn.classList.remove('loading');
    searchBtn.disabled = false;
    // 同时还原 loading 的标签
    if (state.activeLoadingTag) {
        state.activeLoadingTag.classList.remove('loading');
        state.activeLoadingTag = null;
    }
}

function setTagLoading(tag) {
    if (state.activeLoadingTag) state.activeLoadingTag.classList.remove('loading');
    state.activeLoadingTag = tag;
    if (tag) tag.classList.add('loading');
}

function cancelActiveSSE() {
    if (state.activeSSE) {
        state.activeSSE.cancel();
        state.activeSSE = null;
    }
}

// ===== 工具函数 =====

function scoreBar(value, max, label) {
    if (!max) max = 100; if (!label) label = '';
    var pct = Math.round((value / max) * 100);
    var filled = Math.round(pct / 10);
    var empty = 10 - filled;
    var emoji = pct >= 80 ? '🟩' : pct >= 60 ? '🟨' : pct >= 40 ? '🟧' : '🟥';
    return '<div class="score-row">' +
        '<span class="score-label">' + label + '</span>' +
        '<span class="score-bar">' + emoji + ' ' + '█'.repeat(filled) + '░'.repeat(empty) + ' ' + value + '/' + max + '</span>' +
        '</div>';
}

function recommendationBadge(rec) {
    var map = {
        '强烈推荐': { cls: 'rec-strong', icon: '✅' },
        '可尝试': { cls: 'rec-try', icon: '⚠️' },
        '谨慎进入': { cls: 'rec-caution', icon: '⛔' },
        '不建议': { cls: 'rec-no', icon: '❌' },
    };
    var m = map[rec] || { cls: 'rec-try', icon: '❓' };
    return '<span class="rec-badge ' + m.cls + '">' + m.icon + ' ' + rec + '</span>';
}

function fireIcon(count) {
    if (count >= 3) return '🔥🔥🔥';
    if (count >= 2) return '🔥🔥';
    if (count >= 1) return '🔥';
    return '';
}

function tagChips(tags) {
    if (!tags || tags.length === 0) return '';
    return tags.map(function (t) { return '<span class="tag-chip">' + t + '</span>'; }).join('');
}

// 复制报告到剪贴板
function copyReport() {
    var reportEl = document.getElementById('stream-report');
    var text = reportEl ? reportEl.textContent : '';
    if (!text.trim()) { showToast('没有可复制的内容', 'warning'); return; }
    navigator.clipboard.writeText(text).then(function () {
        showToast('报告已复制到剪贴板', 'success');
    }).catch(function () {
        showToast('复制失败，请手动选中复制', 'error');
    });
}

// ===== API 调用 =====

async function fetchOpportunities() {
    var resp = await fetch('/api/opportunities');
    if (!resp.ok) throw new Error('获取机会排行失败');
    return await resp.json();
}

async function fetchCategoryDetail(catName) {
    var resp = await fetch('/api/opportunities/' + encodeURIComponent(catName));
    if (!resp.ok) throw new Error('获取品类详情失败');
    return await resp.json();
}

async function fetchTrending() {
    var resp = await fetch('/api/trending');
    if (!resp.ok) throw new Error('获取热词失败');
    return await resp.json();
}

async function refreshTrending() {
    var resp = await fetch('/api/trending/refresh', { method: 'POST' });
    if (!resp.ok) throw new Error('刷新热词失败');
    return await resp.json();
}

async function triggerCrawl(category) {
    var resp = await fetch('/api/crawl', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: category, count: 15 }),
    });
    if (!resp.ok) throw new Error('触发爬虫失败');
    return await resp.json();
}

// ===== SSE 流式洞察（核心改造）=====
function streamInsight(category) {
    cancelActiveSSE();

    // 打开详情弹出层 + 显示加载布局
    detailOverlay.style.display = 'flex';
    detailOverlay.scrollTop = 0;
    detailContent.innerHTML =
        '<div class="detail-header">' +
        '<h2>' + category + '</h2>' +
        '<span class="rec-badge rec-try">⏳ 分析中</span>' +
        '</div>' +
        '<div id="stage-list" class="stage-list" style="margin-bottom:16px;"></div>' +
        '<div id="stream-report" class="insight-report" style="min-height:80px;color:#888;">正在连接...</div>';

    var stageList = document.getElementById('stage-list');
    var reportEl = document.getElementById('stream-report');
    var stages = {};
    var fullReport = '';
    var noteCount = 0;

    function addStage(stageId, message) {
        if (stages[stageId]) return;
        stages[stageId] = true;
        stageList.innerHTML +=
            '<div class="progress-stage" data-stage="' + stageId + '">' +
            '<span class="stage-dot"></span>' +
            '<span>' + message + '</span>' +
            '</div>';
    }

    function completeStage(stageId) {
        var el = stageList.querySelector('[data-stage="' + stageId + '"]');
        if (el) el.classList.add('complete');
    }

    function handleSSEEvent(type, rawData) {
        try {
            var payload = JSON.parse(rawData);

            if (type === 'stage') {
                addStage(payload.stage, payload.message);
                // 标记已完成阶段（stages ending with "ed" or "done_generate"）
                if (/ed$/.test(payload.stage) || payload.stage === 'done_generate') {
                    completeStage(payload.stage);
                }
                // 爬虫阶段特殊提示
                if (payload.stage === 'crawl') {
                    showToast('知识库数据不足，正在从小红书实时抓取，预计 30-60 秒...', 'warning');
                }
                if (payload.stage === 'login') {
                    showToast('请在浏览器扫码登录小红书...', 'warning');
                }
            } else if (type === 'token') {
                fullReport += payload.token;
                reportEl.textContent = fullReport;
                // 自动跟滚到底部
                reportEl.scrollIntoView({ behavior: 'smooth', block: 'end' });
            } else if (type === 'done') {
                noteCount = payload.note_count || 0;
                reportEl.style.color = '#333';
                onStreamDone();
            } else if (type === 'error') {
                reportEl.textContent = fullReport || payload.message;
                reportEl.style.color = '#cc2222';
                showToast(payload.message, 'error');
                onStreamDone();
            }
        } catch (e) {
            // 非 JSON 的 SSE 行，忽略
        }
    }

    function onStreamDone() {
        state.activeSSE = null;
        // 尝试用 REST API 补充结构化指标
        fetchCategoryDetail(category).then(function (data) {
            if (data && data.scores) {
                renderDetail(data, fullReport);
            } else {
                _renderStreamOnly(category, fullReport, noteCount);
            }
        }).catch(function () {
            _renderStreamOnly(category, fullReport, noteCount);
        }).finally(function () {
            unlockSearch();
        });
    }

    // 发起 fetch + ReadableStream
    fetch('/api/insight/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: category }),
    }).then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);

        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';
        var cancelled = false;

        // 创建可取消的包装
        state.activeSSE = {
            cancel: function () {
                cancelled = true;
                try { reader.cancel(); } catch (_) { }
            }
        };

        function readStream() {
            reader.read().then(function (result) {
                if (cancelled) return;
                if (result.done) {
                    if (reportEl.textContent === '正在连接...') {
                        reportEl.textContent = '';
                    }
                    onStreamDone();
                    return;
                }

                buffer += decoder.decode(result.value, { stream: true });
                var parts = buffer.split('\n\n');
                buffer = parts.pop() || '';

                for (var i = 0; i < parts.length; i++) {
                    var part = parts[i].trim();
                    if (!part) continue;

                    var lines = part.split('\n');
                    var evType = '';
                    var evData = '';

                    for (var j = 0; j < lines.length; j++) {
                        var line = lines[j];
                        if (line.indexOf('event: ') === 0) {
                            evType = line.slice(7).trim();
                        } else if (line.indexOf('data: ') === 0) {
                            evData = line.slice(6).trim();
                        } else if (line.indexOf('data:') === 0) {
                            evData = line.slice(5).trim();
                        }
                    }

                    if (evData) {
                        handleSSEEvent(evType || 'stage', evData);
                    }
                    if (evData && evType === 'done') break;
                }

                readStream();
            }).catch(function (err) {
                if (cancelled) return;
                console.error('SSE read error:', err);
                showToast('连接中断: ' + err.message, 'error');
                unlockSearch();
            });
        }

        readStream();
    }).catch(function (err) {
        console.error('SSE fetch error:', err);
        reportEl.textContent = '无法连接到服务';
        reportEl.style.color = '#cc2222';
        showToast('服务连接失败: ' + err.message, 'error');
        unlockSearch();
    });
}

function _renderStreamOnly(category, report, noteCount) {
    detailContent.innerHTML =
        '<div class="detail-header">' +
        '<h2>' + category + '</h2>' +
        '<div style="display:flex;gap:8px;align-items:center;">' +
        '<span class="rec-badge rec-try">📊 实时报告</span>' +
        '<button class="btn-primary btn-small" onclick="copyReport()" style="font-size:12px;">📋 复制报告</button>' +
        '</div>' +
        '</div>' +
        '<div class="result-container" style="margin-bottom:16px;">' +
        '<div id="stream-report" class="insight-report">' + (report || '报告生成中...') + '</div>' +
        '</div>' +
        '<div style="display:flex;justify-content:space-between;align-items:center;">' +
        '<span style="font-size:13px;color:var(--text-secondary);">分析笔记：' + (noteCount || '—') + ' 篇</span>' +
        '</div>';
}

// ===== 搜索入口（带防重复）=====
function showCategoryDetail(catName) {
    if (state.isSearching) {
        showToast('请求处理中，请稍候...', 'warning');
        return;
    }
    lockSearch();
    state.activeCategory = catName;
    streamInsight(catName);
}

// ===== 渲染函数 =====

function renderRankingList(opportunities) {
    if (!opportunities || opportunities.length === 0) {
        rankingList.innerHTML = '<div class="empty-state">' +
            '<div class="empty-icon">📊</div>' +
            '<p>暂无品类数据</p>' +
            '<p style="font-size:13px;color:var(--text-secondary);margin-top:8px;">请在上方搜索框输入品类名，系统会自动抓取小红书数据</p>' +
            '</div>';
        return;
    }

    var fireLevels = {};
    opportunities.forEach(function (o, i) {
        if (i < 3) fireLevels[o.category] = 3;
        else if (i < 6) fireLevels[o.category] = 2;
        else if (i < 10) fireLevels[o.category] = 1;
        else fireLevels[o.category] = 0;
    });

    var html = '';
    opportunities.forEach(function (o, idx) {
        var s = o.scores;
        var fire = fireIcon(fireLevels[o.category]);
        var rec = recommendationBadge(o.recommendation);
        var rank = idx + 1;
        var crawlBadge = o.crawl_needed
            ? '<span class="tag-chip" style="background:#fff0e0;color:#cc6600;">📡 需采集</span>'
            : '';

        html +=
            '<div class="ranking-item" data-category="' + o.category + '" tabindex="0" role="button">' +
            '<div class="rank-number">' + rank + '</div>' +
            '<div class="rank-body">' +
            '<div class="rank-header">' +
            '<span class="rank-name">' + o.category + '</span>' +
            '<span class="rank-fire">' + fire + '</span>' +
            '<span class="rank-score">' + s.overall + '/100</span>' +
            rec +
            '</div>' +
            '<div class="rank-tags">' + crawlBadge + ' ' + tagChips(o.tags) + '</div>' +
            '<div class="rank-metrics">' +
            '<span>💰 利润 ' + s.profit + '</span>' +
            '<span>🚚 物流 ' + s.logistics + '</span>' +
            '<span>📊 需求 ' + s.demand + '</span>' +
            '<span>⚖️ 竞争 ' + s.competition + '</span>' +
            '</div>' +
            '</div>' +
            '<div class="rank-arrow">›</div>' +
            '</div>';
    });

    rankingList.innerHTML = html;
}

function renderFallbackDetail(catName) {
    var html =
        '<div class="detail-header">' +
        '<h2>' + catName + '</h2>' +
        '<span class="rec-badge rec-try">⚠️ 待验证</span>' +
        '</div>' +
        '<div class="crawl-banner">' +
        '<span>📡 暂无数据，需要从小红书采集（约 30-60 秒）</span>' +
        '<button class="btn-primary btn-small" onclick="doCrawl(\'' + catName + '\')">开始采集</button>' +
        '</div>' +
        '<div class="detail-scores">' +
        '<h3>📊 核心指标（估算）</h3>' +
        scoreBar(65, 100, '💰 利润空间') +
        scoreBar(55, 100, '🚚 物流友好') +
        scoreBar(60, 100, '📊 市场需求') +
        scoreBar(50, 100, '⚖️ 竞争强度') +
        '<div class="score-divider"></div>' +
        scoreBar(58, 100, '🎯 综合评分（估算）') +
        '</div>' +
        '<div class="detail-checklist">' +
        '<h3>🎯 建议操作</h3>' +
        '<label class="check-item"><input type="checkbox"> 先在小红书搜索「' + catName + '」了解市场</label>' +
        '<label class="check-item"><input type="checkbox"> 点击「开始采集」获取真实数据</label>' +
        '</div>';
    detailContent.innerHTML = html;
}

function renderDetail(data, streamedReport) {
    var s = data.scores;
    var m = data.metrics;
    var isEstimated = data.estimated;
    var needsCrawl = data.crawl_needed;

    var baseCost = m.avg_cost > 0 ? m.avg_cost : 25;
    var entryPrice = Math.round(baseCost * 2.5);
    var midPrice = Math.round(baseCost * 4);
    var highPrice = Math.round(baseCost * 6.5);
    var hasEcomData = m.avg_price > 0 && m.avg_cost > 0;

    var crawlingBanner = needsCrawl ?
        '<div class="crawl-banner">' +
        '<span>📡 此品类数据不完整，建议从小红书采集（约 30-60 秒）</span>' +
        '<button class="btn-primary btn-small" onclick="doCrawl(\'' + data.category + '\')">开始采集</button>' +
        '</div>' : '';

    var estimatedBadge = isEstimated ? '<span class="rec-badge rec-try">📊 估算数据</span>' : '';

    var reportSection = streamedReport ?
        '<div class="detail-scores">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">' +
        '<h3 style="margin:0;">📝 AI 洞察报告</h3>' +
        '<button class="btn-primary btn-small" onclick="copyReport()" style="font-size:12px;">📋 复制报告</button>' +
        '</div>' +
        '<div id="stream-report" class="insight-report">' + streamedReport + '</div>' +
        '</div>' : '';

    var diffsSection = data.differentiation_directions && data.differentiation_directions.length > 0 ?
        '<div class="detail-diffs"><h3>🎯 差异化方向</h3><ul class="diff-list">' +
        data.differentiation_directions.map(function (d) { return '<li>' + d + '</li>'; }).join('') +
        '</ul></div>' : '';

    var html =
        '<div class="detail-header">' +
        '<h2>' + data.category + '</h2>' +
        '<div style="display:flex;gap:8px;align-items:center;">' +
        estimatedBadge +
        recommendationBadge(data.recommendation) +
        '</div>' +
        '</div>' +
        crawlingBanner +
        '<div class="detail-scores">' +
        '<h3>📊 核心指标</h3>' +
        scoreBar(s.profit, 100, '💰 利润空间') +
        scoreBar(s.logistics, 100, '🚚 物流友好') +
        scoreBar(s.demand, 100, '📊 市场需求') +
        scoreBar(s.competition, 100, '⚖️ 竞争强度 (越高越蓝海)') +
        '<div class="score-divider"></div>' +
        scoreBar(s.overall, 100, '🎯 综合评分') +
        '</div>' +
        '<div class="detail-metrics">' +
        '<h3>📋 关键数据</h3>' +
        '<div class="metrics-grid">' +
        '<div class="metric-item"><span class="metric-val">' + (hasEcomData || isEstimated ? '¥' + m.avg_price : '暂无') + '</span><span class="metric-lbl">平均售价</span></div>' +
        '<div class="metric-item"><span class="metric-val">' + (hasEcomData || isEstimated ? '¥' + m.avg_cost : '暂无') + '</span><span class="metric-lbl">平均成本</span></div>' +
        '<div class="metric-item"><span class="metric-val">' + (hasEcomData || isEstimated ? Math.round(m.avg_profit_margin * 100) + '%' : '暂无') + '</span><span class="metric-lbl">平均利润率</span></div>' +
        '<div class="metric-item"><span class="metric-val">' + (m.avg_monthly_sales > 0 ? m.avg_monthly_sales.toLocaleString() : (isEstimated ? m.avg_monthly_sales.toLocaleString() : '暂无')) + '</span><span class="metric-lbl">预估月销</span></div>' +
        '<div class="metric-item"><span class="metric-val">' + (hasEcomData ? m.avg_weight + 'kg' : (isEstimated ? m.avg_weight + 'kg' : '暂无')) + '</span><span class="metric-lbl">平均重量</span></div>' +
        '<div class="metric-item"><span class="metric-val">' + m.brand_count + '</span><span class="metric-lbl">品牌数量</span></div>' +
        '</div>' +
        '</div>' +
        '<div class="detail-sourcing">' +
        '<h3>📦 拿货参考</h3>' +
        '<table class="sourcing-table">' +
        '<thead><tr><th>产品方向</th><th>参考成本</th><th>预估售价</th></tr></thead>' +
        '<tbody>' +
        '<tr><td>基础款 (引流)</td><td>¥' + baseCost + '</td><td>¥' + entryPrice + '</td></tr>' +
        '<tr><td>升级款 (主力)</td><td>¥' + Math.round(baseCost * 1.8) + '</td><td>¥' + midPrice + '</td></tr>' +
        '<tr><td>高端款 (品牌)</td><td>¥' + Math.round(baseCost * 3.2) + '</td><td>¥' + highPrice + '</td></tr>' +
        '</tbody>' +
        '</table>' +
        '<div class="sourcing-tip">💡 建议去 <strong>1688</strong> 搜索「' + data.category + '」，选月销 500+、回头率 30%+ 的店铺</div>' +
        '</div>' +
        reportSection +
        diffsSection +
        '<div class="detail-checklist">' +
        '<h3>🎯 你的执行清单</h3>' +
        '<label class="check-item"><input type="checkbox"> 去 1688 找 2-3 家供应商，对比样品质量</label>' +
        '<label class="check-item"><input type="checkbox"> 分析小红书评论，确定 ' + data.category + ' 的核心需求</label>' +
        '<label class="check-item"><input type="checkbox"> 参考定价策略：引流款 ¥' + entryPrice + '、主力款 ¥' + midPrice + '</label>' +
        '<label class="check-item"><input type="checkbox"> 主图突出核心卖点，参考品类热门笔记风格</label>' +
        '<label class="check-item"><input type="checkbox"> 上架后跟踪数据，优化主图和关键词</label>' +
        '</div>';

    detailContent.innerHTML = html;
    detailOverlay.scrollTop = 0;
}

// ===== 爬虫触发（增强 UX）=====

window.doCrawl = async function (category) {
    var triggerBtns = document.querySelectorAll('.crawl-banner .btn-small');
    triggerBtns.forEach(function (b) {
        b.disabled = true;
        b.textContent = '⏳ 采集中...';
    });

    showToast('正在从小红书采集「' + category + '」数据，预计 30-60 秒...', 'warning');

    try {
        var result = await triggerCrawl(category);
        if (result.success) {
            showToast('✅ 已采集 ' + (result.count || '—') + ' 篇笔记，正在刷新报告...', 'success');
            setTimeout(function () {
                showCategoryDetail(category);
            }, 1500);
        } else {
            showToast('采集失败: ' + (result.message || '未知错误'), 'error');
            triggerBtns.forEach(function (b) {
                b.disabled = false;
                b.textContent = '开始采集';
            });
        }
    } catch (err) {
        showToast('采集请求失败: ' + err.message, 'error');
        triggerBtns.forEach(function (b) {
            b.disabled = false;
            b.textContent = '开始采集';
        });
    }
};

// ===== 事件委托 =====

rankingList.addEventListener('click', function (e) {
    var target = e.target;
    while (target && target !== rankingList) {
        if (target.classList.contains('ranking-item')) {
            var cat = target.dataset.category;
            if (cat) showCategoryDetail(cat);
            return;
        }
        target = target.parentElement;
    }
});

// ===== 搜索处理（防抖 + 去重）=====

var searchTimeout = null;
function handleSearch(query) {
    var trimmed = query.trim();
    if (!trimmed) return;

    if (state.isSearching) {
        showToast('请求处理中，请稍候...', 'warning');
        return;
    }

    if (searchTimeout) clearTimeout(searchTimeout);
    searchTimeout = setTimeout(function () {
        showCategoryDetail(trimmed);
    }, 200);
}

// ===== 热词渲染 =====

function renderTrendingTags(items) {
    var container = document.getElementById('trending-tags');
    if (!items || items.length === 0) {
        container.innerHTML = '<span style="color:var(--text-secondary);font-size:13px;">暂无热词数据</span>';
        return;
    }

    var trendIcons = { up: '📈', stable: '➡️', seasonal: '📅' };
    var trendClasses = { up: 'trend-up', stable: 'trend-stable', seasonal: 'trend-seasonal' };

    container.innerHTML = '';
    items.forEach(function (item) {
        var tag = document.createElement('span');
        tag.className = 'trending-tag';
        tag.innerHTML =
            '<span class="trend-hot">' + item.hots + '</span>' +
            item.keyword +
            '<span class="' + (trendClasses[item.trend] || 'trend-stable') + '">' + (trendIcons[item.trend] || '') + '</span>';
        tag.title = '热度: ' + item.hots + ' | 分类: ' + item.category;
        tag.addEventListener('click', function () {
            if (state.isSearching) {
                showToast('请求处理中，请稍候...', 'warning');
                return;
            }
            setTagLoading(tag);
            categoryInput.value = item.keyword;
            showCategoryDetail(item.keyword);
        });
        container.appendChild(tag);
    });
}

// ===== 初始化 =====

async function init() {
    loadingEl.style.display = 'flex';

    // 加载热词
    try {
        var trendingData = await fetchTrending();
        renderTrendingTags(trendingData.items || []);
    } catch (err) {
        console.warn('热词加载失败:', err);
        document.getElementById('trending-tags').innerHTML =
            '<span style="color:var(--text-secondary);font-size:13px;">热词数据暂不可用</span>';
    }

    // 刷新热词按钮
    document.getElementById('refresh-trending-btn').addEventListener('click', async function () {
        var btn = document.getElementById('refresh-trending-btn');
        btn.disabled = true;
        btn.textContent = '刷新中...';
        try {
            var result = await refreshTrending();
            renderTrendingTags(result.items || []);
            btn.textContent = '🔄 已刷新';
            showToast('热词已更新', 'success');
            setTimeout(function () { btn.textContent = '🔄 刷新'; btn.disabled = false; }, 2000);
        } catch (err) {
            btn.textContent = '刷新失败';
            showToast('热词刷新失败: ' + err.message, 'error');
            setTimeout(function () { btn.textContent = '🔄 刷新'; btn.disabled = false; }, 2000);
        }
    });

    // 加载品类排行
    var data = await fetchOpportunities();
    state.opportunities = data.opportunities || [];
    totalBadge.textContent = '共 ' + (data.total || state.opportunities.length) + ' 个品类';

    renderRankingList(state.opportunities);

    // 填充快速标签
    var cats = state.opportunities.slice(0, 6).map(function (o) { return o.category; });
    cats.forEach(function (c) {
        var tag = document.createElement('span');
        tag.className = 'quick-tag';
        tag.textContent = c;
        tag.addEventListener('click', function () {
            if (state.isSearching) {
                showToast('请求处理中，请稍候...', 'warning');
                return;
            }
            setTagLoading(tag);
            showCategoryDetail(c);
        });
        quickTags.appendChild(tag);
    });

    // 填充 datalist
    state.opportunities.forEach(function (o) {
        var opt = document.createElement('option');
        opt.value = o.category;
        suggestions.appendChild(opt);
    });

    loadingEl.style.display = 'none';

    // 搜索事件
    searchBtn.addEventListener('click', function () {
        handleSearch(categoryInput.value);
    });

    categoryInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') handleSearch(categoryInput.value);
    });
}

// ===== 关闭详情 =====
detailClose.addEventListener('click', function () {
    cancelActiveSSE();
    unlockSearch();
    detailOverlay.style.display = 'none';
});

detailOverlay.addEventListener('click', function (e) {
    if (e.target === detailOverlay) {
        cancelActiveSSE();
        unlockSearch();
        detailOverlay.style.display = 'none';
    }
});

// ESC 关闭
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && detailOverlay.style.display === 'flex') {
        cancelActiveSSE();
        unlockSearch();
        detailOverlay.style.display = 'none';
    }
});

// ===== 启动 =====
document.addEventListener('DOMContentLoaded', init);
