import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Projects from './pages/Projects'
import ProjectDetail from './pages/ProjectDetail'
import ChapterReader from './pages/ChapterReader'
import Onboarding from './pages/Onboarding'
import Run from './pages/Run'
import RunDetail from './pages/RunDetail'
import Review from './pages/Review'
import Style from './pages/Style'
import Settings from './pages/Settings'
import Acceptance from './pages/Acceptance'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="projects" element={<Projects />} />
          <Route path="projects/:id" element={<ProjectDetail />} />
          <Route path="projects/:projectId/chapters/:chapterNumber" element={<ChapterReader />} />
          <Route path="onboarding" element={<Onboarding />} />
          <Route path="run" element={<Run />} />
          <Route path="runs/:runId" element={<RunDetail />} />
          <Route path="review" element={<Review />} />
          <Route path="style" element={<Style />} />
          <Route path="settings" element={<Settings />} />
          <Route path="acceptance" element={<Acceptance />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
