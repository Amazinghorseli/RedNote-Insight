export const HISTORY_KEY = 'rni_search_history';
export const MAX_HISTORY = 10;

export const RECOMMENDATION_MAP = {
  '强烈推荐': { cls: 'rec-strong', icon: '✅' },
  '可尝试': { cls: 'rec-try', icon: '⚠️' },
  '谨慎进入': { cls: 'rec-caution', icon: '⛔' },
  '不建议': { cls: 'rec-no', icon: '❌' },
};

export const TYPE_LABEL = { both: '🛒+🎬', selection: '🛒', topic: '🎬' };
export const TYPE_CLASS = {
  both: 'insp-tag-both',
  selection: 'insp-tag-sel',
  topic: 'insp-tag-topic',
};

export const TREND_ICONS = { up: '📈', stable: '➡️', seasonal: '📅' };
export const TREND_CLASSES = { up: 'trend-up', stable: 'trend-stable', seasonal: 'trend-seasonal' };
