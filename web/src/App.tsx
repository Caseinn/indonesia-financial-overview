import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { SiteShell } from "@/components/site-shell"
import { DashboardPage } from "@/pages/dashboard"
import { GuidePage } from "@/pages/guide"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<SiteShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="guide" element={<GuidePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
