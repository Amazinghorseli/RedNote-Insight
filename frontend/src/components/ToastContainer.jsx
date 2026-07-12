import React, { useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';

const ICONS = { error: '✕', success: '✓', warning: '⚠', info: 'ℹ' };

function ToastItem({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss(toast.id);
    }, 5000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <div className={'toast-item toast-' + (toast.type || 'info')}>
      <span className="toast-icon">{ICONS[toast.type] || 'ℹ'}</span>
      <span>{toast.message}</span>
    </div>
  );
}

export default function ToastContainer() {
  const { state, dismissToast } = useApp();
  const { toasts } = state;

  const handleDismiss = useCallback(
    (id) => dismissToast(id),
    [dismissToast]
  );

  return (
    <div className="toast-container">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={handleDismiss} />
      ))}
    </div>
  );
}
