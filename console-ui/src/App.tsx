import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import Workspace from './pages/Workspace'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/run/:runDir" element={<Workspace />} />
      </Route>
    </Routes>
  )
}
