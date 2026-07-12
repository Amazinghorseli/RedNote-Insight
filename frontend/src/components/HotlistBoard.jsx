import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useApp } from '../context/AppContext';
import { fetchInspiration } from '../api/client';
import { TYPE_LABEL, TYPE_CLASS } from '../utils/constants';

export default function HotlistBoard() {
  const { showToast, setTab, openOverlay } = useApp();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState('全部');
  const [error, setError] = useState(null);

  const load = useCallback(async (category) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchInspiration(category);
      setItems(data.items || []);
      setActiveFilter('全部');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const categories = useMemo(() => {
    const cats = ['全部'];
    items.forEach((item) => {
      if (item.category && !cats.includes(item.category)) {
        cats.push(item.category);
      }
    });
    return cats;
  }, [items]);

  const filtered = useMemo(() => {
    if (activeFilter === '全部') return items;
    return items.filter((i) => i.category === activeFilter);
  }, [items, activeFilter]);

  const handleItemClick = (keyword) => {
    setTab('discover');
    openOverlay(keyword, 'selection');
  };

  const handleRefresh = async () => {
    setLoading(true);
    try {
      await load();
      showToast('灵感库已加载', 'success');
    } catch {
      showToast('加载失败', 'error');
    }
  };

  const dateStr = new Date().toLocaleDateString('zh-CN', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
  });

  return (
    <div className="hero-section" style={{ marginBottom: '24px' }}>
      <h1 className="hero-title">💡 灵感库</h1>
      <p className="hero-desc">
        不知道搜什么？按品类浏览精选方向，每条都保证有数据，点一下就是选品+选题双报告。
      </p>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
          📅 <span id="hotlist-date">{dateStr} · 灵感</span>
        </span>
        <button className="btn-text" onClick={handleRefresh} disabled={loading}>
          {loading ? '加载中...' : '🔄 刷新'}
        </button>
      </div>

      {categories.length > 1 && (
        <div className="hotlist-filters" style={{ marginTop: '12px' }}>
          {categories.map((cat) => (
            <span
              key={cat}
              className={'hotlist-filter' + (activeFilter === cat ? ' active' : '')}
              onClick={() => setActiveFilter(cat)}
            >
              {cat}
            </span>
          ))}
        </div>
      )}

      {loading ? (
        <div className="loading-indicator" style={{ display: 'flex', marginTop: '24px' }}>
          <div className="loading-spinner"></div>
          <span>加载中...</span>
        </div>
      ) : error ? (
        <div className="empty-state" style={{ marginTop: '24px' }}>
          <div className="empty-icon">⚠️</div>
          <p>加载失败：{error}</p>
        </div>
      ) : (
        <div className="hotlist-board" style={{ marginTop: '16px' }}>
          {filtered.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">🔍</div>
              <p>该分类暂无灵感</p>
            </div>
          ) : (
            filtered.map((item, idx) => {
              const rank = idx + 1;
              let medal = '';
              if (rank === 1) medal = '🥇';
              else if (rank === 2) medal = '🥈';
              else if (rank === 3) medal = '🥉';

              return (
                <div
                  key={item.keyword + idx}
                  className="hotlist-item"
                  tabIndex={0}
                  role="button"
                  onClick={() => handleItemClick(item.keyword)}
                  onKeyDown={(e) => e.key === 'Enter' && handleItemClick(item.keyword)}
                >
                  <div className="hotlist-rank">
                    {medal || <span className="rank-num">{rank}</span>}
                  </div>
                  <div className="hotlist-body">
                    <div className="hotlist-top">
                      <span className="hotlist-keyword">{item.keyword}</span>
                      <span className={'insp-tag ' + (TYPE_CLASS[item.type] || 'insp-tag-topic')}>
                        {TYPE_LABEL[item.type] || '🎬'}
                      </span>
                      <span className="hotlist-cat-tag">{item.category}</span>
                    </div>
                    <div className="hotlist-tip">💡 {item.tip || ''}</div>
                  </div>
                  <div className="hotlist-arrow">›</div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
