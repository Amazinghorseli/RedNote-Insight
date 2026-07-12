import React, { createContext, useContext, useReducer, useCallback, useRef } from 'react';

const AppContext = createContext(null);

// --- Actions ---
const SET_TAB = 'SET_TAB';
const OPEN_OVERLAY = 'OPEN_OVERLAY';
const CLOSE_OVERLAY = 'CLOSE_OVERLAY';
const ADD_TOAST = 'ADD_TOAST';
const REMOVE_TOAST = 'REMOVE_TOAST';

// --- Reducer ---
function reducer(state, action) {
  switch (action.type) {
    case SET_TAB:
      return { ...state, activeTab: action.payload };

    case OPEN_OVERLAY:
      return {
        ...state,
        overlay: {
          open: true,
          category: action.payload.category,
          defaultTab: action.payload.defaultTab || 'selection',
        },
      };

    case CLOSE_OVERLAY:
      return { ...state, overlay: { open: false, category: null, defaultTab: 'selection' } };

    case ADD_TOAST: {
      const id = Date.now() + Math.random();
      const toast = { id, message: action.payload.message, type: action.payload.type || 'info' };
      return { ...state, toasts: [...state.toasts, toast] };
    }

    case REMOVE_TOAST:
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.payload) };

    default:
      return state;
  }
}

const initialState = {
  activeTab: 'discover',
  overlay: { open: false, category: null, defaultTab: 'selection' },
  toasts: [],
};

// --- Provider ---
export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  // Abort controller ref for SSE cancellation
  const abortRef = useRef(null);

  const showToast = useCallback((message, type = 'info') => {
    dispatch({ type: ADD_TOAST, payload: { message, type } });
  }, []);

  const dismissToast = useCallback((id) => {
    dispatch({ type: REMOVE_TOAST, payload: id });
  }, []);

  const openOverlay = useCallback((category, defaultTab = 'selection') => {
    dispatch({ type: OPEN_OVERLAY, payload: { category, defaultTab } });
  }, []);

  const closeOverlay = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    dispatch({ type: CLOSE_OVERLAY });
  }, []);

  const setTab = useCallback((tab) => {
    dispatch({ type: SET_TAB, payload: tab });
  }, []);

  const value = {
    state,
    dispatch,
    showToast,
    dismissToast,
    openOverlay,
    closeOverlay,
    setTab,
    abortRef,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}

export { SET_TAB, OPEN_OVERLAY, CLOSE_OVERLAY, ADD_TOAST, REMOVE_TOAST };
