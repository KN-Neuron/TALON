import { Link } from 'react-router-dom'
import '../App.css'

function NotFoundPage({ id }: { id: string }) {
  return (
    <main className="page">
      <h1 className="title">Camera not found</h1>
      <p>There is no camera streaming with id "{id}".</p>
      <Link to="/">
        <button type="button">Back to camera list</button>
      </Link>
    </main>
  )
}

export default NotFoundPage
