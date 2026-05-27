import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import SiteSettings from './pages/SiteSettings'
import CrawlResults from './pages/CrawlResults'
import OcrUsage from './pages/OcrUsage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/sites" element={<SiteSettings />} />
        <Route path="/results" element={<CrawlResults />} />
        <Route path="/admin/ocr" element={<OcrUsage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
