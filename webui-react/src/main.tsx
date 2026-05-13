import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Search from './pages/Search';
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
      <NavLink to="/" end className={linkClass}>Dashboard</NavLink>
      <NavLink to="/search" className={linkClass}>Search</NavLink>
      <NavLink to="/wm" className={linkClass}>Working Memory</NavLink>
      <NavLink to="/review" className={linkClass}>Review</NavLink>
      <div className="mt-4 px-4 py-1 text-xs text-gray-600 uppercase">Canvas</div>
      <NavLink to="/canvas/graph" className={linkClass}>Memory Graph</NavLink>
      <NavLink to="/canvas/heatmap" className={linkClass}>Heatmap</NavLink>
      <NavLink to="/canvas/timeline" className={linkClass}>Timeline</NavLink>
      <NavLink to="/canvas/projection" className={linkClass}>Vector Projection</NavLink>
      <div className="mt-4 px-4 py-1 text-xs text-gray-600 uppercase">System</div>
      <NavLink to="/health" className={linkClass}>Health</NavLink>
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
            <Route path="/search" element={<Search />} />
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
