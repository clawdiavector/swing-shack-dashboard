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
import { Images } from './pages/studio/Images'
import { Memes } from './pages/studio/Memes'
import { Ideas } from './pages/calendar/Ideas'
import { Lanes } from './pages/calendar/Lanes'
import { Gbp } from './pages/publish/Gbp'
import { PostizPage } from './pages/publish/PostizPage'
import { Queue } from './pages/publish/Queue'
import { Week } from './pages/results/Week'
import { Worked } from './pages/results/Worked'

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
        <Route path="create/images" element={<Images />} />
        <Route path="create/memes" element={<Memes />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="calendar/ideas" element={<Ideas />} />
        <Route path="calendar/lanes" element={<Lanes />} />
        <Route path="publish" element={<Publish />} />
        <Route path="publish/queue" element={<Queue />} />
        <Route path="publish/postiz" element={<PostizPage />} />
        <Route path="publish/gbp" element={<Gbp />} />
        <Route path="results" element={<Results />} />
        <Route path="results/week" element={<Week />} />
        <Route path="results/worked" element={<Worked />} />
        <Route path="ops" element={<Ops />} />
        <Route path="other" element={<Other />} />
        <Route path="desk" element={<Desk />} />
        <Route path="tool/:slug" element={<Tool />} />
        <Route path="*" element={<Navigate to="/daily" replace />} />
      </Route>
    </Routes>
  )
}
