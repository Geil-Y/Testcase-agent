import { BrowserRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import Home from './pages/Home';
import Workspace from './pages/Workspace';
import RequirementDetail from './pages/RequirementDetail';
import PromptLearning from './pages/PromptLearning';

type PageKey = 'case-generation' | 'prompt-learning';

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();

  const activePage: PageKey = location.pathname.startsWith('/prompt-learning')
    ? 'prompt-learning'
    : 'case-generation';

  function goPage(page: PageKey) {
    if (page === 'case-generation') {
      navigate('/');
    } else {
      navigate('/prompt-learning');
    }
  }

  return (
    <div className="app-shell">
      <aside className="app-nav">
        <div className="app-nav-brand">
          <span>◇</span> Pipeline Console
        </div>
        <div className="app-nav-items">
          <button
            className={`app-nav-item ${activePage === 'case-generation' ? 'active' : ''}`}
            onClick={() => goPage('case-generation')}
          >
            Case Generation
          </button>
          <button
            className={`app-nav-item ${activePage === 'prompt-learning' ? 'active' : ''}`}
            onClick={() => goPage('prompt-learning')}
          >
            Prompt Learning
          </button>
        </div>
      </aside>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/requirements/:id" element={<RequirementDetail />} />
          <Route path="/runs/:runId" element={<Workspace />} />
          <Route path="/prompt-learning" element={<PromptLearning />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}
