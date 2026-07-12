import React, { useState, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { fetchTrending, refreshTrending } from '../api/client';
import { TREND_ICONS, TREND_CLASSES } from '../utils/constants';

export default function TrendingTags() {
  const { showToast, openOverlay } = useApp();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingTag, setLoadingTag] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchTrending();
      setItems(data.items || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const data = await refreshTrending();
      setItems(data.items || []);
      showToast('热词已更新', 'success');
    } catch (err) {
      showToast('热词刷新失败: ' + err.message, 'error');
    } finally {
      setTimeout(() => setRefreshing(false), 2000);
    }
  };

  const handleTagClick = (keyword) => {
    setLoadingTag(keyword);
    openOverlay(keyword, 'selection');
  };

  if (loading) {
    return (
      <div className="trending-section">
        <div className="section-header">
          <h2>🔍 小红书搜索热词</h2>
          <button className="btn-text">🔄 刷新</button>
        </div>
        <div className="trending-tags">
          <div className="skeleton-block">
            <div className="skeleton skeleton-line medium"></div>
            <div className="skeleton skeleton-line short"></div>
            <div className="skeleton skeleton-line medium"></div>
            <div className="skeleton skeleton-line short"></div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="trending-section">
      <div className="section-header">
        <h2>🔍 小红书搜索热词</h2>
        <button
          className="btn-text"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          {refreshing ? '刷新中...' : '🔄 刷新'}
        </button>
      </div>
      <div className="trending-tags" id="trending-tags">
        {items.length === 0 ? (
          <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>暂无热词数据</span>
        ) : (
          items.map((item) => (
            <span
              key={item.keyword}
              className={'trending-tag' + (loadingTag === item.keyword ? ' loading' : '')}
              title={'热度: ' + item.hots + ' | 分类: ' + item.category}
              onClick={() => handleTagClick(item.keyword)}
            >
              <span className="trend-hot">{item.hots}</span>
              {item.keyword}
              <span className={TREND_CLASSES[item.trend] || 'trend-stable'}>
                {TREND_ICONS[item.trend] || ''}
              </span>
            </span>
          ))
        )}
      </div>
    </div>
  );
}
