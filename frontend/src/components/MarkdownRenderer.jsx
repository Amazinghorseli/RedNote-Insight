import React, { useMemo } from 'react';
import { renderMarkdown } from '../utils/markdown';

export default function MarkdownRenderer({ text, className = '' }) {
  const html = useMemo(() => renderMarkdown(text), [text]);

  return (
    <div
      className={'insight-report rendered ' + className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
