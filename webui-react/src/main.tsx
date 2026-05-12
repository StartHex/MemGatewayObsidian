import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Search from './pages/Search';
import MemoryGraph from './components/MemoryGraph';
import { HealthReport } from './pages/Health';
import './index.css';

function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen">
        <nav className="w-48 bg-gray-900 p-4 flex flex-col gap-2">
          <NavLink to="/" className="text-sm hover:text-blue-400">Dashboard</NavLink>
          <NavLink to="/search" className="text-sm hover:text-blue-400">Search</NavLink>
          <NavLink to="/canvas/graph" className="text-sm hover:text-blue-400">Memory Graph</NavLink>
          <NavLink to="/canvas/heatmap" className="text-sm hover:text-blue-400">Heatmap</NavLink>
          <NavLink to="/canvas/timeline" className="text-sm hover:text-blue-400">Timeline</NavLink>
          <NavLink to="/canvas/projection" className="text-sm hover:text-blue-400">Vector Proj</NavLink>
          <NavLink to="/health" className="text-sm hover:text-blue-400">Health</NavLink>
        </nav>
        <main className="flex-1 p-6 overflow-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/search" element={<Search />} />
            <Route path="/canvas/graph" element={<MemoryGraph />} />
            <Route path="/canvas/heatmap" element={<div>Heatmap Canvas</div>} />
            <Route path="/canvas/timeline" element={<div>Timeline Canvas</div>} />
            <Route path="/canvas/projection" element={<div>Vector Projection Canvas</div>} />
            <Route path="/health" element={<HealthReport />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(<App />);
