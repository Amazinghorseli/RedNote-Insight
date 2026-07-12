import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useApp } from '../context/AppContext';
import useSSE from '../hooks/useSSE';
import MarkdownRenderer from './MarkdownRenderer';
import { renderMarkdown } from '../utils/markdown';

export default function DetailOverlay() {
  const { state, closeOverlay, showToast } = useApp();
  const { category, defaultTab } = state.overlay;

  const [activeTab, setActiveTab] = useState(defaultTab || 'selection');
  const sse = useSSE();
  const startedRef = useRef(false);

  // Start SSE on mount
  useEffect(() => {
    if (!startedRef.current && category) {
      startedRef.current = true;
      sse.start(category, {
        onError: (err) => {
          showToast('连接中断: ' + err.message, 'error');
        },
      });
    }
    return () => { sse.abort(); };
  }, [category]); // eslint-disable-line react-hooks/exhaustive-deps

  // Cleanup on unmount: abort SSE
  useEffect(() => {
    return () => { sse.abort(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ESC key handler
  useEffect(() => {
    function handleKey(e) {
      if (e.key === 'Escape') closeOverlay();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [closeOverlay]);

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) closeOverlay();
  };

  // Copy individual report
  const copyReport = useCallback((text) => {
    if (!text || !text.trim()) {
      showToast('没有可复制的内容', 'warning');
      return;
    }
    navigator.clipboard.writeText(text).then(() => {
      showToast('报告已复制到剪贴板', 'success');
    }).catch(() => {
      showToast('复制失败，请手动选中复制', 'error');
    });
  }, [showToast]);

  const copyAll = useCallback(() => {
    const sel = sse.selectionReport;
    const cr = sse.creatorReport;
    if (!sel && !cr) {
      showToast('两份报告都还没生成完，请稍候', 'warning');
      return;
    }
    let combined = '';
    if (sel) combined += '# 📊 选品报告\n\n' + sel + '\n\n---\n\n';
    if (cr) combined += '# 🎬 选题方案\n\n' + cr;
    navigator.clipboard.writeText(combined).then(() => {
      showToast('✅ 两份方案已一键复制！直接粘贴到备忘录/飞书/Notion 即可', 'success');
    }).catch(() => {
      showToast('复制失败，请手动选中复制', 'error');
    });
  }, [sse.selectionReport, sse.creatorReport, showToast]);

  const downloadAll = useCallback(() => {
    const sel = sse.selectionReport;
    const cr = sse.creatorReport;
    if (!sel && !cr) { showToast('没有可下载的内容', 'warning'); return; }

    let combined = '';
    if (sel) combined += '# 📊 选品报告\n\n' + sel;
    if (cr) combined += '\n\n---\n\n# 🎬 选题方案\n\n' + cr;
    combined += '\n\n---\n*由 RedNote-Insight 生成 · ' + new Date().toLocaleDateString('zh-CN') + '*';

    const fname = (category || '报告') + '_双报告_' + new Date().toISOString().slice(0, 10) + '.md';
    const blob = new Blob([combined], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('✅ Markdown 已下载: ' + fname, 'success');
  }, [category, sse.selectionReport, sse.creatorReport, showToast]);

  const printReport = useCallback(() => {
    const sel = sse.selectionReport;
    const cr = sse.creatorReport;
    if (!sel && !cr) { showToast('没有可打印的内容', 'warning'); return; }

    const printWindow = window.open('', '_blank');
    let content = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>选品报告</title>';
    content += '<style>body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.8;max-width:720px;margin:40px auto;padding:0 20px;color:#333;}h1{font-size:22px;border-bottom:2px solid #ff5a5f;padding-bottom:8px;}h2{font-size:18px;color:#ff5a5f;}h3{font-size:15px;}strong{color:#ff5a5f;}table{width:100%;border-collapse:collapse;margin:10px 0;}th{background:#fff0f0;color:#ff5a5f;padding:8px 12px;text-align:left;border:1px solid #e0e0e0;}td{padding:7px 12px;border:1px solid #e0e0e0;}hr{border:none;border-top:2px solid #ff5a5f;margin:16px 0;}ul,ol{padding-left:20px;}@media print{body{margin:0;padding:10mm;}}';
    content += '</style></head><body>';
    if (sel) {
      content += '<h1>📊 选品报告</h1>' + renderMarkdown(sel);
    }
    if (cr) {
      content += '<hr style="margin:30px 0">';
      content += '<h1>🎬 选题方案</h1>' + renderMarkdown(cr);
    }
    content += '<p style="color:#999;font-size:12px;margin-top:30px;">由 RedNote-Insight 生成 · ' + new Date().toLocaleDateString('zh-CN') + '</p>';
    content += '</body></html>';
    printWindow.document.write(content);
    printWindow.document.close();
    setTimeout(() => { printWindow.print(); }, 300);
  }, [sse.selectionReport, sse.creatorReport, showToast]);

  const bothDone = sse.selectionDone && sse.creatorDone;

  const renderStreamingContent = (report, done) => {
    if (done && report) {
      return <MarkdownRenderer text={report} />;
    }
    if (report) {
      return (
        <div style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '13px', color: '#555' }}>
          {report}
        </div>
      );
    }
    return (
      <div className="skeleton-block">
        <div className="skeleton skeleton-heading"></div>
        <div className="skeleton skeleton-line medium"></div>
        <div className="skeleton skeleton-line short"></div>
        <div className="skeleton skeleton-line medium"></div>
        <div className="skeleton skeleton-line short"></div>
      </div>
    );
  };

  const renderStageList = () => {
    if (sse.stageList.length === 0) return null;
    return (
      <div id="stage-list" className="stage-list" style={{ marginBottom: '16px' }}>
        {sse.stageList.map((s) => (
          <div
            key={s.id}
            className={'progress-stage' + (s.complete ? ' complete' : '')}
          >
            <span className="stage-dot"></span>
            <span>{s.message}</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="detail-overlay" style={{ display: 'flex' }} onClick={handleOverlayClick}>
      <div className="detail-card" id="detail-card">
        <button className="detail-close" onClick={closeOverlay}>×</button>

        {/* Export Bar */}
        {bothDone && (
          <div className="export-bar" id="export-bar">
            <span className="export-hint">⬇️ 两份报告已就绪</span>
            <button className="btn-export" onClick={copyAll}>📋 一键复制全部</button>
            <button className="btn-export btn-export-alt" onClick={() => copyReport(sse.selectionReport)}>📊 仅复制选品</button>
            <button className="btn-export btn-export-alt" onClick={() => copyReport(sse.creatorReport)}>🎬 仅复制选题</button>
            <button className="btn-download" onClick={downloadAll} title="下载完整报告为 Markdown 文件">📥 下载 .md</button>
            <button className="btn-print" onClick={printReport} title="打印为 PDF">🖨️ 打印 PDF</button>
          </div>
        )}

        {/* Header */}
        <div className="detail-header">
          <h2>{category}</h2>
          <span className={'rec-badge ' + (sse.error ? 'rec-caution' : (bothDone ? 'rec-strong' : 'rec-try'))}>
            {sse.statusText}
          </span>
        </div>

        {/* Stage list */}
        {renderStageList()}

        {/* Error state */}
        {sse.error && !sse.selectionReport && !sse.creatorReport && (
          <div className="error-state">
            <div className="error-icon">⚠️</div>
            <p>{sse.error}</p>
            <div className="sse-error-actions">
              <button className="btn-retry" onClick={() => sse.start(category)}>🔄 重试</button>
            </div>
          </div>
        )}

        {/* Dual Tabs */}
        <div className="detail-tabs">
          <button
            className={'detail-tab' + (activeTab === 'selection' ? ' active' : '')}
            onClick={() => setActiveTab('selection')}
          >
            📊 选品报告{sse.selectionDone ? ' ✓' : ''}
          </button>
          <button
            className={'detail-tab' + (activeTab === 'creator' ? ' active' : '')}
            onClick={() => setActiveTab('creator')}
          >
            🎬 选题方案{sse.creatorDone ? ' ✓' : ''}
          </button>
        </div>

        {/* Selection Panel */}
        {activeTab === 'selection' && (
          <div className="detail-tab-content" style={{ display: 'block' }}>
            {renderStreamingContent(sse.selectionReport, sse.selectionDone)}
          </div>
        )}

        {/* Creator Panel */}
        {activeTab === 'creator' && (
          <div className="detail-tab-content" style={{ display: 'block' }}>
            {renderStreamingContent(sse.creatorReport, sse.creatorDone)}
          </div>
        )}
      </div>
    </div>
  );
}
