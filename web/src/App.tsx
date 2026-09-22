import { Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { CalendarPage } from './pages/CalendarPage'
import { Create } from './pages/Create'
import { Daily } from './pages/Daily'
import { Desk } from './pages/Desk'
import { Other } from './pages/Other'
import { Publish } from './pages/Publish'
import { Results } from './pages/Results'
import { Review } from './pages/Review'
import { ReviewPiece } from './pages/ReviewPiece'
import { Ops } from './pages/Ops'
import { Tool } from './pages/Tool'
import { BuildPost } from './pages/studio/BuildPost'
import { Captions } from './pages/studio/Captions'
import { Copy } from './pages/studio/Copy'

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/daily" replace />} />
        <Route path="daily" element={<Daily />} />
        <Route path="review" element={<Review />} />
        <Route path="review/:itemId" element={<ReviewPiece />} />
        <Route path="create" element={<Create />} />
        <Route path="create/post" element={<BuildPost />} />
        <Route path="create/captions" element={<Captions />} />
        <Route path="create/copy" element={<Copy />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="publish" element={<Publish />} />
        <Route path="results" element={<Results />} />
        <Route path="ops" element={<Ops />} />
        <Route path="other" element={<Other />} />
        <Route path="desk" element={<Desk />} />
        <Route path="tool/:slug" element={<Tool />} />
        <Route path="*" element={<Navigate to="/daily" replace />} />
      </Route>
    </Routes>
  )
}
