export function renderMarkdown(text) {
  if (!text) return '';
  const lines = text.split('\n');
  let html = '';
  let inTable = false;
  let inList = false;
  let inCodeBlock = false;
  let i = 0;

  function closeList() {
    if (inList) { html += '</ul>\n'; inList = false; }
  }
  function closeTable() {
    if (inTable) { html += '</tbody></table>\n'; inTable = false; }
  }
  function flushInline(t) {
    t = t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
    return t;
  }

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      closeList();
      i++;
      continue;
    }

    if (trimmed.startsWith('```')) {
      closeList(); closeTable();
      if (inCodeBlock) { html += '</code></pre>\n'; inCodeBlock = false; }
      else { html += '<pre><code>'; inCodeBlock = true; }
      i++;
      continue;
    }
    if (inCodeBlock) {
      html += line + '\n';
      i++;
      continue;
    }

    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      closeList();
      const cells = trimmed.split('|').filter((c) => c.trim());
      if (cells.every((c) => /^[:]?[-]{2,}[:]?$/.test(c.trim()))) {
        i++;
        continue;
      }
      if (!inTable) {
        html += '<table><thead><tr>';
        cells.forEach((c) => { html += '<th>' + flushInline(c.trim()) + '</th>'; });
        html += '</tr></thead><tbody>\n';
        inTable = true;
      } else {
        html += '<tr>';
        cells.forEach((c) => { html += '<td>' + flushInline(c.trim()) + '</td>'; });
        html += '</tr>\n';
      }
      i++;
      continue;
    }
    closeTable();

    if (/^[━]{3,}$/.test(trimmed) || /^[-*_]{3,}$/.test(trimmed)) {
      closeList();
      html += '<hr>\n';
      i++;
      continue;
    }

    if (trimmed.startsWith('### ')) { closeList(); html += '<h3>' + flushInline(trimmed.slice(4)) + '</h3>\n'; i++; continue; }
    if (trimmed.startsWith('## '))  { closeList(); html += '<h2>' + flushInline(trimmed.slice(3)) + '</h2>\n'; i++; continue; }
    if (trimmed.startsWith('# '))   { closeList(); html += '<h1>' + flushInline(trimmed.slice(2)) + '</h1>\n'; i++; continue; }

    if (/^【.+】/.test(trimmed)) { closeList(); html += '<h2>' + flushInline(trimmed) + '</h2>\n'; i++; continue; }

    if (/^[-*]\s/.test(trimmed) || /^\d+[.)]\s/.test(trimmed)) {
      if (!inList) { html += '<ul>\n'; inList = true; }
      const liText = trimmed.replace(/^[-*\d]+[.)]\s*/, '');
      html += '<li>' + flushInline(liText) + '</li>\n';
      i++;
      continue;
    }
    closeList();

    html += '<p>' + flushInline(trimmed) + '</p>\n';
    i++;
  }

  closeList();
  closeTable();
  if (inCodeBlock) { html += '</code></pre>\n'; }
  return html;
}
