import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import Home from './pages/Home';
import Workspace from './pages/Workspace';
import RequirementDetail from './pages/RequirementDetail';

function Nav() {
  const location = useLocation();
  const isHome = location.pathname === '/';
  const isWorkspace = location.pathname.startsWith('/runs/');

  return (
    <nav className="nav">
      <Link to="/" className="nav-brand" style={{ textDecoration: 'none' }}>
        <span>◇</span> Pipeline Console
      </Link>
      <div className="nav-sep" />
      <Link to="/" className={`nav-item ${isHome ? 'active' : ''}`} style={{ textDecoration: 'none' }}>
        Requirements
      </Link>
      {isWorkspace && (
        <span className="nav-item active">Workspace</span>
      )}
    </nav>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/requirements/:id" element={<RequirementDetail />} />
        <Route path="/runs/:runId" element={<Workspace />} />
      </Routes>
    </BrowserRouter>
  );
}
