import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { fetchOpportunities } from '../api/client';
import useSearchHistory from '../hooks/useSearchHistory';
import useDebounce from '../hooks/useDebounce';

export default function SearchBox() {
  const { state, showToast, openOverlay } = useApp();
  const { history, saveHistory, clearHistory } = useSearchHistory();

  const [query, setQuery] = useState('');
  const [quickTags, setQuickTags] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [loadingTag, setLoadingTag] = useState(null);

  const searchLocked = useRef(false);
  const inputRef = useRef(null);

  // Load quick tags from opportunities
  useEffect(() => {
    fetchOpportunities()
      .then((data) => {
        const cats = (data.opportunities || []).slice(0, 6).map((o) => o.category);
        setQuickTags(cats);
        setSuggestions(data.opportunities || []);
      })
      .catch(() => {});
  }, []);

  const doSearch = useCallback((keyword, defaultTab = 'selection') => {
    if (!keyword || !keyword.trim()) return;
    if (searchLocked.current) {
      showToast('请求处理中，请稍候...', 'warning');
      return;
    }
    searchLocked.current = true;
    setIsSearching(true);
    setQuery(keyword.trim());
    saveHistory(keyword.trim());
    openOverlay(keyword.trim(), defaultTab);
  }, [showToast, openOverlay, saveHistory]);

  const [debouncedSearch] = useDebounce(doSearch, 200);

  const handleSearch = () => {
    if (!query.trim()) return;
    doSearch(query, 'selection');
  };

  const handleAgent = () => {
    if (!query.trim()) {
      showToast('请输入品类名', 'warning');
      return;
    }
    debouncedSearch(query, 'creator');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      if (!query.trim()) return;
      debouncedSearch(query, 'selection');
    }
  };

  const handleQuickTag = (cat) => {
    setLoadingTag(cat);
    setQuery(cat);
    doSearch(cat, 'selection');
  };

  const handleHistoryClick = (keyword) => {
    setQuery(keyword);
    doSearch(keyword, 'selection');
  };

  // Reset lock when overlay closes
  useEffect(() => {
    if (!state.overlay.open && searchLocked.current) {
      setIsSearching(false);
      setLoadingTag(null);
      searchLocked.current = false;
    }
  }, [state.overlay.open]);

  return (
    <div className="input-card">
      <div className="input-row">
        <input
          ref={inputRef}
          type="text"
          className="main-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入品类名，例如：辣条、磁吸感应灯"
          list="category-suggestions"
        />
        <datalist id="category-suggestions">
          {suggestions.map((o) => (
            <option key={o.category} value={o.category} />
          ))}
        </datalist>
        <button
          className={'btn-primary' + (isSearching ? ' loading' : '')}
          onClick={handleSearch}
          disabled={isSearching}
        >
          🔍 选品分析
        </button>
        <button
          className={'btn-agent' + (isSearching ? ' loading' : '')}
          onClick={handleAgent}
          disabled={isSearching}
        >
          🎬 博主方案
        </button>
      </div>

      {quickTags.length > 0 && (
        <div className="quick-tags">
          <span className="quick-tag-label">热门：</span>
          {quickTags.map((cat) => (
            <span
              key={cat}
              className={'quick-tag' + (loadingTag === cat ? ' loading' : '')}
              onClick={() => handleQuickTag(cat)}
            >
              {cat}
            </span>
          ))}
        </div>
      )}

      {history.length > 0 && (
        <div className="search-history" style={{ display: 'flex' }}>
          <span className="history-label">🕐 最近搜索：</span>
          {history.map((h) => (
            <span
              key={h.keyword + h.time}
              className="history-item"
              onClick={() => handleHistoryClick(h.keyword)}
            >
              {h.keyword}
            </span>
          ))}
          <span className="history-clear" onClick={clearHistory} title="清除搜索历史">
            ✕
          </span>
        </div>
      )}
    </div>
  );
}
