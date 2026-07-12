import React, { useState, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { fetchOpportunities } from '../api/client';
import { RECOMMENDATION_MAP } from '../utils/constants';

function fireIcon(idx) {
  if (idx < 3) return '🔥🔥🔥';
  if (idx < 6) return '🔥🔥';
  if (idx < 10) return '🔥';
  return '';
}

function recBadge(rec) {
  const m = RECOMMENDATION_MAP[rec] || { cls: 'rec-try', icon: '❓' };
  return (
    <span className={'rec-badge ' + m.cls}>
      {m.icon} {rec}
    </span>
  );
}

function tagChips(tags) {
  if (!tags || tags.length === 0) return null;
  return tags.map((t, i) => (
    <span key={i} className="tag-chip">{t}</span>
  ));
}

export default function RankingsList() {
  const { openOverlay } = useApp();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchOpportunities();
      setItems(data.opportunities || []);
      setTotal(data.total || (data.opportunities || []).length);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleClick = (cat) => {
    openOverlay(cat, 'selection');
  };

  return (
    <div id="rankings-section">
      <div className="section-header">
        <h2>🔥 本周热门品类机会</h2>
        <span className="section-badge" id="total-badge">
          {loading ? '加载中...' : '共 ' + total + ' 个品类'}
        </span>
      </div>

      <div className="ranking-list" id="ranking-list">
        {loading ? (
          <div className="skeleton-block">
            <div className="skeleton skeleton-heading"></div>
            <div className="skeleton skeleton-line medium"></div>
            <div className="skeleton skeleton-line short"></div>
            <div className="skeleton skeleton-line medium"></div>
            <div className="skeleton skeleton-line short"></div>
            <div className="skeleton skeleton-line medium"></div>
          </div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📊</div>
            <p>暂无品类数据</p>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '8px' }}>
              请在上方搜索框输入品类名，系统会自动抓取小红书数据
            </p>
          </div>
        ) : (
          items.map((o, idx) => {
            const s = o.scores || {};
            return (
              <div
                key={o.category}
                className="ranking-item"
                tabIndex={0}
                role="button"
                onClick={() => handleClick(o.category)}
                onKeyDown={(e) => e.key === 'Enter' && handleClick(o.category)}
              >
                <div className="rank-number">{idx + 1}</div>
                <div className="rank-body">
                  <div className="rank-header">
                    <span className="rank-name">{o.category}</span>
                    <span className="rank-fire">{fireIcon(idx)}</span>
                    <span className="rank-score">{s.overall}/100</span>
                    {recBadge(o.recommendation)}
                  </div>
                  <div className="rank-tags">
                    {o.crawl_needed && (
                      <span className="tag-chip" style={{ background: '#fff0e0', color: '#cc6600' }}>
                        📡 需采集
                      </span>
                    )}
                    {tagChips(o.tags)}
                  </div>
                  <div className="rank-metrics">
                    <span>💰 利润 {s.profit}</span>
                    <span>🚚 物流 {s.logistics}</span>
                    <span>📊 需求 {s.demand}</span>
                    <span>⚖️ 竞争 {s.competition}</span>
                  </div>
                </div>
                <div className="rank-arrow">›</div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
