import React from 'react';
import { useApp } from '../context/AppContext';

export default function Sidebar() {
  const { state, setTab } = useApp();
  const { activeTab } = state;

  const tabs = [
    { id: 'hotlist', icon: '💡', label: '灵感库' },
    { id: 'discover', icon: '🎯', label: '发现机会' },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo">💡 选品雷达</div>
        <div className="tagline">小红书选品 · 机会评分 · 执行清单</div>
      </div>
      <nav className="nav-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={'nav-tab' + (activeTab === tab.id ? ' active' : '')}
            onClick={() => setTab(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="version">v3.0 · 选品雷达</div>
      </div>
    </aside>
  );
}
