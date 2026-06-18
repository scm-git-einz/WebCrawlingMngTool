import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import SiteSettings from './pages/SiteSettings'
import CrawlResults from './pages/CrawlResults'
import OcrUsage from './pages/OcrUsage'
import Matrix from './pages/Matrix'
import LlmUsage from './pages/LlmUsage'
import LogMonitoring from './pages/LogMonitoring'
import FailureMonitoring from './pages/FailureMonitoring'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/matrix" element={<Matrix />} />
        <Route path="/sites" element={<SiteSettings />} />
        <Route path="/results" element={<CrawlResults />} />
        <Route path="/admin/ocr" element={<OcrUsage />} />
        <Route path="/admin/llm" element={<LlmUsage />} />
        <Route path="/admin/logs" element={<LogMonitoring />} />
        <Route path="/admin/failures" element={<FailureMonitoring />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
