import React from 'react';
import { useApp } from './context/AppContext';
import Sidebar from './components/Sidebar';
import SearchBox from './components/SearchBox';
import TrendingTags from './components/TrendingTags';
import RankingsList from './components/RankingsList';
import HotlistBoard from './components/HotlistBoard';
import DetailOverlay from './components/DetailOverlay';
import ToastContainer from './components/ToastContainer';

export default function App() {
  const { state } = useApp();
  const { activeTab, overlay } = state;

  return (
    <div className="app-container">
      <Sidebar />

      <main className="main-content" id="main-content">
        {/* --- 发现机会 Tab --- */}
        <div className={'tab-content' + (activeTab === 'discover' ? ' active' : '')} id="tab-discover">
          <div className="hero-section">
            <h1 className="hero-title">🔍 选品雷达 + 选题引擎</h1>
            <p className="hero-desc">
              输入品类名，一键生成两套方案。<strong>选品分析</strong>看商机，<strong>博主方案</strong>看脚本——博主直接复制就能拍。
            </p>
            <SearchBox />
          </div>
          <TrendingTags />
          <RankingsList />
        </div>

        {/* --- 灵感库 Tab --- */}
        <div className={'tab-content' + (activeTab === 'hotlist' ? ' active' : '')} id="tab-hotlist">
          <HotlistBoard />
        </div>
      </main>

      {/* --- 详情弹窗 --- */}
      {overlay.open && <DetailOverlay />}

      {/* --- Toast 通知 --- */}
      <ToastContainer />
    </div>
  );
}
