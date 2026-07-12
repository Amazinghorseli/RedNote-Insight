const BASE = '';

async function request(url, options = {}) {
  const resp = await fetch(BASE + url, options);
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(text || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export function fetchOpportunities() {
  return request('/api/opportunities');
}

export function fetchCategoryDetail(catName) {
  return request('/api/opportunities/' + encodeURIComponent(catName));
}

export function fetchTrending() {
  return request('/api/trending');
}

export function refreshTrending() {
  return request('/api/trending/refresh', { method: 'POST' });
}

export function fetchInspiration(category) {
  let url = '/api/inspiration';
  if (category) url += '?category=' + encodeURIComponent(category);
  return request(url);
}

export function triggerCrawl(category) {
  return request('/api/crawl', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, count: 15 }),
  });
}

export function streamInsight(category, { onEvent, onDone, onError, signal }) {
  const controller = new AbortController();
  const combinedSignal = signal
    ? (() => {
        const s = new AbortController();
        signal.addEventListener('abort', () => s.abort());
        controller.signal.addEventListener('abort', () => s.abort());
        return s.signal;
      })()
    : controller.signal;

  fetch('/api/insight/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category }),
    signal: combinedSignal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error('HTTP ' + response.status);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      function read() {
        reader.read().then(({ done, value }) => {
          if (done) {
            if (onDone) onDone();
            return;
          }
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop() || '';

          for (const part of parts) {
            const trimmed = part.trim();
            if (!trimmed) continue;
            const lines = trimmed.split('\n');
            let evType = '';
            let evData = '';
            for (const line of lines) {
              if (line.startsWith('event: ')) evType = line.slice(7).trim();
              else if (line.startsWith('data: ')) evData = line.slice(6).trim();
              else if (line.startsWith('data:')) evData = line.slice(5).trim();
            }
            if (evData && onEvent) {
              try {
                const payload = JSON.parse(evData);
                onEvent(evType || 'stage', payload);
              } catch {
                /* non-JSON SSE line */
              }
            }
            if (evData && evType === 'done') return;
          }
          read();
        }).catch((err) => {
          if (err.name === 'AbortError') return;
          if (onError) onError(err);
        });
      }
      read();
    })
    .catch((err) => {
      if (err.name === 'AbortError') return;
      if (onError) onError(err);
    });

  return controller;
}
