import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, session } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(session.user)

  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('inventrack:logout', onLogout)
    return () => window.removeEventListener('inventrack:logout', onLogout)
  }, [])

  const login = useCallback(async (email, password) => {
    const data = await api('/auth/login', { method: 'POST', body: { email, password }, auth: false })
    session.save(data.access_token, data.user)
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(() => {
    session.clear()
    setUser(null)
  }, [])

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
