import { Route, Routes } from 'react-router-dom'
import HomePage from './pages/HomePage'
import StreamPage from './pages/StreamPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/:id" element={<StreamPage />} />
    </Routes>
  )
}

export default App
