/**
 * app.js — 小红书爆款雷达 前端逻辑
 * =========================================
 * 纯原生 JS，零依赖，SPA 模式
 */
(function () {
    'use strict';

    // ============================================================
    // DOM 元素
    // ============================================================
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // Tab
    const tabBtns = $$('.nav-tab');
    const tabContents = $$('.tab-content');

    // Insight
    const insightInput = $('#insight-input');
    const insightBtn = $('#insight-btn');
    const insightResult = $('#insight-result');

    // QA
    const qaInput = $('#qa-input');
    const qaBtn = $('#qa-btn');
    const chatMessages = $('#chat-messages');

    // Evaluate
    const evalBtn = $('#eval-btn');
    const evalResult = $('#eval-result');

    // Stats
    const statCategories = $('#stat-categories');
    const statNotes = $('#stat-notes');
    const statChunks = $('#stat-chunks');

    // Toast
    const toast = $('#toast');

    // ============================================================
    // 工具函数
    // ============================================================
    function showToast(msg, duration = 3000) {
        toast.textContent = msg;
        toast.style.display = 'block';
        toast.style.animation = 'none';
        toast.offsetHeight;
        toast.style.animation = 'slideUp 0.3s ease';
        clearTimeout(toast._timeout);
        toast._timeout = setTimeout(() => { toast.style.display = 'none'; }, duration);
    }

    function setLoading(btn, loading) {
        const text = btn.querySelector('.btn-text');
        const spinner = btn.querySelector('.btn-loading');
        if (loading) {
            btn.disabled = true;
            if (text) text.style.display = 'none';
            if (spinner) spinner.style.display = 'inline-flex';
        } else {
            btn.disabled = false;
            if (text) text.style.display = 'inline';
            if (spinner) spinner.style.display = 'none';
        }
    }

    async function apiPost(url, body) {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        return resp.json();
    }

    // ============================================================
    // Tab 切换
    // ============================================================
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            tabContents.forEach(tc => tc.classList.remove('active'));
            const target = $(`#tab-${btn.dataset.tab}`);
            if (target) target.classList.add('active');
        });
    });

    // ============================================================
    // Stats 加载
    // ============================================================
    async function loadStats() {
        try {
            const resp = await fetch('/api/stats');
            const data = await resp.json();
            if (data.success) {
                statCategories.textContent = data.categories.length;
                statNotes.textContent = data.total_notes;
                statChunks.textContent = data.total_chunks;
            } else {
                statCategories.textContent = '—';
                statNotes.textContent = '—';
                statChunks.textContent = '—';
            }
        } catch (e) {
            console.warn('Stats 加载失败:', e);
        }
    }
    loadStats();

    // ============================================================
    // Insight 模式
    // ============================================================
    insightInput.addEventListener('input', () => {
        insightBtn.disabled = !insightInput.value.trim();
    });

    insightBtn.addEventListener('click', async () => {
        const category = insightInput.value.trim();
        if (!category) return;

        setLoading(insightBtn, true);

        // 创建报告容器
        insightResult.innerHTML = '<div class="insight-report">';
        const reportEl = insightResult.querySelector('.insight-report');

        // 状态指示器
        const statusEl = document.createElement('div');
        statusEl.className = 'stream-status';
        statusEl.innerHTML = '<div class="spinner" style="border-color:#ccc;border-top-color:#ff5a5f;width:24px;height:24px;"></div> <span class="status-text">正在分析「<strong>' + escapeHtml(category) + '</strong>」...</span>';
        reportEl.appendChild(statusEl);

        // 报告内容区
        const contentEl = document.createElement('pre');
        contentEl.style.cssText = 'white-space:pre-wrap;font-family:inherit;line-height:1.8;display:none;';
        reportEl.appendChild(contentEl);

        // 底部统计
        const footerEl = document.createElement('p');
        footerEl.style.cssText = 'margin-top:12px;color:#999;font-size:12px;display:none;';
        reportEl.appendChild(footerEl);

        try {
            const resp = await fetch('/api/insight/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || `HTTP ${resp.status}`);
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let fullText = '';
            let noteCount = 0;
            let elapsed = 0;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                let eventType = '';
                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.slice(7).trim();
                    } else if (line.startsWith('data: ')) {
                        const data = JSON.parse(line.slice(6));

                        if (eventType === 'stage') {
                            statusEl.querySelector('.status-text').textContent = data.message;
                        } else if (eventType === 'token') {
                            if (!contentEl.style.display || contentEl.style.display === 'none') {
                                contentEl.style.display = 'block';
                                statusEl.style.display = 'none';
                            }
                            fullText += data.token;
                            contentEl.textContent = fullText;
                        } else if (eventType === 'done') {
                            noteCount = data.note_count;
                            elapsed = data.elapsed;
                        } else if (eventType === 'error') {
                            throw new Error(data.message);
                        }
                    }
                }
            }

            if (fullText) {
                footerEl.textContent = '⏱ 耗时 ' + elapsed + 's · 基于 ' + noteCount + ' 篇笔记';
                footerEl.style.display = 'block';
                showToast('✅ 报告生成完成 · 耗时 ' + elapsed + 's');
            } else {
                contentEl.textContent = '未能生成报告内容';
                contentEl.style.display = 'block';
            }

            loadStats();

        } catch (e) {
            insightResult.innerHTML = '<div class="empty-state"><div class="empty-icon">❌</div><p>' + escapeHtml(e.message) + '</p></div>';
            showToast('❌ ' + e.message);
        } finally {
            setLoading(insightBtn, false);
        }
    });

    insightInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && insightInput.value.trim()) insightBtn.click();
    });

    // 快速标签
    $$('.quick-tag').forEach(tag => {
        tag.addEventListener('click', () => {
            insightInput.value = tag.dataset.category;
            insightBtn.disabled = false;
            insightBtn.click();
        });
    });

    function renderInsightReport(data) {
        let html = '<div class="insight-report">';
        if (data.generated_count > 0) {
            html += '<p style="color:#ff5a5f;margin-bottom:16px;">📥 已为「<strong>' + escapeHtml(data.category) + '</strong>」实时生成 ' + data.generated_count + ' 篇新笔记</p>';
        }
        html += '<pre style="white-space:pre-wrap;font-family:inherit;line-height:1.8;">' + escapeHtml(data.report) + '</pre>';
        html += '<p style="margin-top:12px;color:#999;font-size:12px;">⏱ 耗时 ' + data.elapsed + 's · 基于 ' + data.notes_count + ' 篇笔记</p>';
        html += '</div>';
        return html;
    }

    // ============================================================
    // QA 模式
    // ============================================================
    qaInput.addEventListener('input', () => {
        qaBtn.disabled = !qaInput.value.trim();
    });

    qaBtn.addEventListener('click', async () => {
        const question = qaInput.value.trim();
        if (!question) return;

        addChatMessage('user', question);
        qaInput.value = '';
        qaBtn.disabled = true;

        const statusEl = addChatMessage('assistant', '<div class="spinner" style="border-color:#ccc;border-top-color:#ff5a5f;"></div> 思考中...');
        const answerEl = document.createElement('div');
        answerEl.className = 'chat-bubble assistant stream-answer';
        answerEl.style.display = 'none';
        chatMessages.appendChild(answerEl);

        let fullAnswer = '';

        try {
            const resp = await fetch('/api/qa/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || `HTTP ${resp.status}`);
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                let eventType = '';
                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.slice(7).trim();
                    } else if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));

                            if (eventType === 'stage') {
                                statusEl.innerHTML = '<div class="spinner" style="border-color:#ccc;border-top-color:#ff5a5f;"></div> ' + escapeHtml(data.message);
                            } else if (eventType === 'token') {
                                if (statusEl.style.display !== 'none') {
                                    statusEl.style.display = 'none';
                                    answerEl.style.display = 'block';
                                }
                                fullAnswer += data.token;
                                answerEl.textContent = fullAnswer;
                                chatMessages.parentElement.scrollTop = chatMessages.parentElement.scrollHeight;
                            } else if (eventType === 'done') {
                                answerEl.textContent = data.answer || fullAnswer;
                                showToast('✅ 回答完成 · 耗时 ' + data.elapsed + 's');
                            } else if (eventType === 'error') {
                                throw new Error(data.message);
                            }
                        } catch (parseErr) {
                            // 非 JSON 数据，跳过
                        }
                    }
                }
            }

            if (!fullAnswer) {
                answerEl.textContent = '未能生成回答';
                answerEl.style.display = 'block';
            }

            if (statusEl.style.display !== 'none') {
                statusEl.style.display = 'none';
            }

        } catch (e) {
            if (statusEl.style.display !== 'none') statusEl.style.display = 'none';
            answerEl.textContent = '❌ ' + escapeHtml(e.message);
            answerEl.style.display = 'block';
            showToast('❌ ' + e.message);
        } finally {
            qaBtn.disabled = false;
        }
    });

    qaInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && qaInput.value.trim()) qaBtn.click();
    });

    function addChatMessage(role, content) {
        const el = document.createElement('div');
        el.className = 'chat-bubble ' + role;
        el.innerHTML = content;
        chatMessages.appendChild(el);
        chatMessages.parentElement.scrollTop = chatMessages.parentElement.scrollHeight;
        return el;
    }

    function updateChatMessage(el, content) {
        if (typeof el === 'string') {
            el = document.getElementById(el);
        }
        el.textContent = content;
        chatMessages.parentElement.scrollTop = chatMessages.parentElement.scrollHeight;
    }

    // ============================================================
    // Evaluate 模式
    // ============================================================
    evalBtn.addEventListener('click', async () => {
        setLoading(evalBtn, true);
        evalResult.innerHTML = '<div class="empty-state"><div class="spinner" style="border-color:#ccc;border-top-color:#ff5a5f;width:32px;height:32px;"></div><p style="margin-top:12px;">正在运行 RAGAS 评估，预计需要 30-60 秒...</p></div>';

        try {
            const data = await apiPost('/api/evaluate', { categories: [] });
            evalResult.innerHTML = renderEvalReport(data);
            showToast(`✅ 评估完成 · 综合评分 ${data.overall_score} 分 · 评级 ${data.grade}`);
        } catch (e) {
            evalResult.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><p>${escapeHtml(e.message)}</p></div>`;
            showToast('❌ ' + e.message);
        } finally {
            setLoading(evalBtn, false);
        }
    });

    function renderEvalReport(data) {
        let html = '';

        // 综合评级
        html += '<div class="eval-grade">';
        html += '<div class="grade-letter">' + escapeHtml(data.grade) + '</div>';
        html += '<div class="grade-label">综合评分 ' + data.overall_score + ' / 100 · ' + data.total_questions + ' 个测试用例</div>';
        html += '</div>';

        // 四维指标
        const scores = data.ragas_scores;
        html += '<div class="eval-summary">';
        html += buildMetricCard('上下文精度', scores.context_precision, '%');
        html += buildMetricCard('上下文召回率', scores.context_recall, '%');
        html += buildMetricCard('忠实度', scores.faithfulness, '%');
        html += buildMetricCard('答案相关性', scores.answer_relevancy, '%');
        html += '</div>';

        // 耗时
        html += '<p style="font-size:13px;color:#999;margin-bottom:16px;">';
        html += '⏱ 平均检索 ' + data.timing_scores.avg_retrieval_ms + 'ms · ';
        html += '平均生成 ' + data.timing_scores.avg_generation_ms + 'ms · ';
        html += '总耗时 ' + data.timing_scores.total_ms + 'ms';
        html += '</p>';

        // 分品类
        if (data.per_category) {
            html += '<h3 style="margin-bottom:12px;font-size:16px;">📊 分品类评估</h3>';
            html += '<div class="eval-per-category">';
            for (const [cat, info] of Object.entries(data.per_category)) {
                html += '<div class="eval-cat-row">';
                html += '<span>' + escapeHtml(cat) + '</span>';
                html += '<span><strong>' + info.score + '</strong> 分</span>';
                html += '<span class="grade-badge grade-' + info.grade + '">' + info.grade + '</span>';
                html += '</div>';
            }
            html += '</div>';
        }

        return html;
    }

    function buildMetricCard(label, value, unit) {
        return (
            '<div class="eval-metric">' +
            '<div class="metric-value">' + value + '<small style="font-size:14px;">' + unit + '</small></div>' +
            '<div class="metric-label">' + label + '</div>' +
            '</div>'
        );
    }

    // ============================================================
    // 工具
    // ============================================================
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ============================================================
    // 初始化
    // ============================================================
    console.log('🎯 小红书爆款雷达 v1.0 已就绪');
    console.log('   📡 API: /api/insight | /api/qa | /api/evaluate');
    console.log('   📊 文档: /docs');
})();
