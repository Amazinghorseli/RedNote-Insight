import { useState, useCallback } from 'react';
import { HISTORY_KEY, MAX_HISTORY } from '../utils/constants';

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export default function useSearchHistory() {
  const [history, setHistory] = useState(loadHistory);

  const saveHistory = useCallback((keyword) => {
    if (!keyword || !keyword.trim()) return;
    const kw = keyword.trim();
    setHistory((prev) => {
      const filtered = prev.filter((h) => h.keyword !== kw);
      const updated = [{ keyword: kw, time: Date.now() }, ...filtered].slice(0, MAX_HISTORY);
      try { localStorage.setItem(HISTORY_KEY, JSON.stringify(updated)); } catch {}
      return updated;
    });
  }, []);

  const clearHistory = useCallback(() => {
    try { localStorage.removeItem(HISTORY_KEY); } catch {}
    setHistory([]);
  }, []);

  return { history, saveHistory, clearHistory };
}
