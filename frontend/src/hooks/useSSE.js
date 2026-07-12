import { useState, useRef, useCallback, useEffect } from 'react';

export default function useSSE() {
  const [stages, setStages] = useState({});
  const [stageList, setStageList] = useState([]);
  const [selectionReport, setSelectionReport] = useState('');
  const [creatorReport, setCreatorReport] = useState('');
  const [selectionDone, setSelectionDone] = useState(false);
  const [creatorDone, setCreatorDone] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [noteCount, setNoteCount] = useState(0);
  const [error, setError] = useState(null);
  const [statusText, setStatusText] = useState('⏳ 分析中');

  const genRef = useRef(0);
  const controllerRef = useRef(null);
  const selectionRef = useRef('');
  const creatorRef = useRef('');

  const reset = useCallback(() => {
    setStages({});
    setStageList([]);
    setSelectionReport('');
    setCreatorReport('');
    setSelectionDone(false);
    setCreatorDone(false);
    setStreaming(false);
    setNoteCount(0);
    setError(null);
    setStatusText('⏳ 分析中');
    selectionRef.current = '';
    creatorRef.current = '';
  }, []);

  const start = useCallback((category, { onError } = {}) => {
    // Cancel previous
    if (controllerRef.current) {
      controllerRef.current.abort();
    }

    genRef.current++;
    const gen = genRef.current;

    reset();
    setStreaming(true);

    const controller = new AbortController();
    controllerRef.current = controller;

    fetch('/api/insight/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error('HTTP ' + response.status);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        function read() {
          reader.read().then(({ done, value }) => {
            if (done || gen !== genRef.current) {
              if (done && gen === genRef.current) handleDone();
              return;
            }

            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop() || '';

            for (const part of parts) {
              if (gen !== genRef.current) return;
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
              if (evData) {
                try {
                  const payload = JSON.parse(evData);
                  handleEvent(evType || 'stage', payload);
                } catch { /* non-JSON */ }
              }
              if (evData && evType === 'done') return;
            }
            read();
          }).catch((err) => {
            if (err.name === 'AbortError') return;
            if (gen === genRef.current) {
              setError(err.message);
              setStreaming(false);
              if (onError) onError(err);
            }
          });
        }
        read();
      })
      .catch((err) => {
        if (err.name === 'AbortError') return;
        if (gen === genRef.current) {
          setError(err.message);
          setStreaming(false);
          if (onError) onError(err);
        }
      });

    function handleEvent(type, payload) {
      if (gen !== genRef.current) return;

      if (type === 'stage') {
        const stageId = payload.stage;
        const message = payload.message;
        setStages((prev) => {
          if (prev[stageId]) return prev;
          return { ...prev, [stageId]: { active: true, message } };
        });
        setStageList((prev) => {
          if (prev.find((s) => s.id === stageId)) return prev;
          return [...prev, { id: stageId, message, complete: false }];
        });

        // Mark complete if ends with "ed" or is a done stage
        const isDone = /ed$/.test(stageId) || stageId === 'selection_done' || stageId === 'creator_done';
        if (isDone) {
          setStageList((prev) =>
            prev.map((s) => (s.id === stageId ? { ...s, complete: true } : s))
          );
        }

        if (stageId === 'crawl') setStatusText('📡 采集中');
        if (stageId === 'login') setStatusText('🔐 需登录');

        if (stageId === 'selection_done') {
          setSelectionDone(true);
          setStatusText('📊 选品完成');
        }
        if (stageId === 'creator_done') {
          setCreatorDone(true);
          setStatusText('✅ 完成');
        }
      } else if (type === 'token:selection') {
        selectionRef.current += payload.token;
        setSelectionReport(selectionRef.current);
      } else if (type === 'token:creator') {
        creatorRef.current += payload.token;
        setCreatorReport(creatorRef.current);
      } else if (type === 'done') {
        setNoteCount(payload.note_count || 0);
        setSelectionDone(true);
        setCreatorDone(true);
        setStatusText('✅ 完成');
        handleDone();
      } else if (type === 'error') {
        setError(payload.message || '未知错误');
        setStreaming(false);
        setStatusText('❌ 失败');
      }
    }

    function handleDone() {
      setStreaming(false);
      controllerRef.current = null;
      // Safety net: render what we have
      if (selectionRef.current && !selectionDone) {
        setSelectionReport(selectionRef.current);
        setSelectionDone(true);
      }
      if (creatorRef.current && !creatorDone) {
        setCreatorReport(creatorRef.current);
        setCreatorDone(true);
      }
    }
  }, [reset]);

  const abort = useCallback(() => {
    genRef.current++;
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
    }
    setStreaming(false);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => { abort(); };
  }, [abort]);

  return {
    stages,
    stageList,
    selectionReport,
    creatorReport,
    selectionDone,
    creatorDone,
    streaming,
    noteCount,
    error,
    statusText,
    start,
    abort,
    reset,
  };
}
