import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="notfound" data-testid="not-found">
      <h1>404</h1>
      <p>La página que buscas no existe.</p>
      <Link className="btn btn-primary" to="/productos">Ir al inicio</Link>
    </div>
  )
}
