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
import { Tool } from './pages/Tool'

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/daily" replace />} />
        <Route path="daily" element={<Daily />} />
        <Route path="review" element={<Review />} />
        <Route path="review/:itemId" element={<ReviewPiece />} />
        <Route path="create" element={<Create />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="publish" element={<Publish />} />
        <Route path="results" element={<Results />} />
        <Route path="other" element={<Other />} />
        <Route path="desk" element={<Desk />} />
        <Route path="tool/:slug" element={<Tool />} />
        <Route path="*" element={<Navigate to="/daily" replace />} />
      </Route>
    </Routes>
  )
}
