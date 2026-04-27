import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Projects from './pages/Projects'
import ProjectDetail from './pages/ProjectDetail'
import Onboarding from './pages/Onboarding'
import Run from './pages/Run'
import RunDetail from './pages/RunDetail'
import Review from './pages/Review'
import Style from './pages/Style'
import Settings from './pages/Settings'

function ChapterRedirect() {
  const path = window.location.pathname
  const match = path.match(/\/projects\/([^/]+)\/chapters\/(\d+)/)
  const projectId = match?.[1]
  const chapterNumber = match?.[2]
  if (projectId && chapterNumber) {
    return <Navigate to={`/projects/${projectId}?chapter=${chapterNumber}&view=content`} replace />
  }
  return <Navigate to="/projects" replace />
}

function RunRedirect() {
  const searchParams = new URLSearchParams(window.location.search)
  const projectId = searchParams.get('project_id')
  const fromChapter = searchParams.get('from_chapter')
  if (projectId && fromChapter) {
    return <Navigate to={`/projects/${projectId}?chapter=${fromChapter}&view=workflow`} replace />
  }
  return <RunDetail />
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="projects" element={<Projects />} />
          <Route path="projects/:id" element={<ProjectDetail />} />
          <Route path="projects/:projectId/chapters/:chapterNumber" element={<ChapterRedirect />} />
          <Route path="onboarding" element={<Onboarding />} />
          <Route path="run" element={<Run />} />
          <Route path="runs/:runId" element={<RunRedirect />} />
          <Route path="review" element={<Review />} />
          <Route path="style" element={<Style />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
