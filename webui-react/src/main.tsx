import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Browse from './pages/Browse';
import WorkingMemory from './pages/WorkingMemory';
import Review from './pages/Review';
import { HealthReport } from './pages/Health';
import MemoryGraph from './components/MemoryGraph';
import Heatmap from './components/Heatmap';
import Timeline from './components/Timeline';
import VectorProj from './components/VectorProj';
import './index.css';

function Sidebar() {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `text-sm ${isActive ? 'active' : ''}`;

  return (
    <nav className="sidebar">
      <div className="px-4 py-2 mb-4">
        <span className="text-lg font-bold">Memory OS</span>
        <div className="text-xs text-gray-500 mt-1">v0.1.0</div>
      </div>

      <NavLink to="/" end className={linkClass}>📊 Dashboard 概览</NavLink>
      <NavLink to="/browse" className={linkClass}>📋 Memories 全部</NavLink>

      <div className="mt-3 px-4 py-1 text-xs text-gray-600 uppercase">工具</div>
      <NavLink to="/wm" className={linkClass}>🧠 工作记忆</NavLink>
      <NavLink to="/review" className={linkClass}>📝 复盘报告</NavLink>

      <div className="mt-3 px-4 py-1 text-xs text-gray-600 uppercase">Canvas 可视化</div>
      <NavLink to="/canvas/graph" className={linkClass}>图谱</NavLink>
      <NavLink to="/canvas/heatmap" className={linkClass}>热力图</NavLink>
      <NavLink to="/canvas/timeline" className={linkClass}>时间线</NavLink>
      <NavLink to="/canvas/projection" className={linkClass}>向量投影</NavLink>

      <div className="mt-3 px-4 py-1 text-xs text-gray-600 uppercase">系统</div>
      <NavLink to="/health" className={linkClass}>🩺 健康检查</NavLink>
    </nav>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen">
        <Sidebar />
        <main className="flex-1 p-6 overflow-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/browse" element={<Browse />} />
            <Route path="/search" element={<Browse />} />
            <Route path="/wm" element={<WorkingMemory />} />
            <Route path="/review" element={<Review />} />
            <Route path="/canvas/graph" element={<MemoryGraph />} />
            <Route path="/canvas/heatmap" element={<Heatmap />} />
            <Route path="/canvas/timeline" element={<Timeline />} />
            <Route path="/canvas/projection" element={<VectorProj />} />
            <Route path="/health" element={<HealthReport />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(<App />);
