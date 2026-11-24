import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import Layout from './components/Layout'
import { ToastProvider } from './components/Toast'
import Login from './pages/Login'
import Products from './pages/Products'
import Users from './pages/Users'
import NotFound from './pages/NotFound'
import { initTelemetry } from './telemetry'
import './styles.css'

initTelemetry()

function Private({ children, admin = false }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (admin && user.role !== 'admin') return <Navigate to="/productos" replace />
  return children
}

function App() {
  const { user } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/productos" replace /> : <Login />} />
      <Route element={<Private><Layout /></Private>}>
        <Route path="/" element={<Navigate to="/productos" replace />} />
        <Route path="/productos" element={<Products />} />
        <Route path="/usuarios" element={<Private admin><Users /></Private>} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
