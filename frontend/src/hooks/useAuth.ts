import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  clearSession,
  getCurrentUser,
  getStoredSession,
  login,
  saveSession,
  signup,
} from '../services/authService'
import type { AuthMode, FeedbackType } from '../types/auth'

export function useAuth() {
  const [mode, setMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [userEmail, setUserEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [feedbackType, setFeedbackType] = useState<FeedbackType>('info')

  const resetSession = useCallback(() => {
    clearSession()
    setIsAuthenticated(false)
    setUserEmail('')
  }, [])

  useEffect(() => {
    const verifySession = async () => {
      const session = getStoredSession()
      if (!session.token) {
        return
      }

      try {
        const user = await getCurrentUser(session.token)
        setUserEmail(user.email)
        setIsAuthenticated(true)
        if (session.email) {
          setUserEmail(session.email)
        }
      } catch {
        resetSession()
      }
    }

    void verifySession()
  }, [resetSession])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (!email.trim() || !password.trim()) {
      setFeedbackType('error')
      setMessage('Please enter both your email and password.')
      return
    }

    setLoading(true)
    setMessage('')

    try {
      if (mode === 'signup') {
        await signup(email, password)
      }

      const tokenData = await login(email, password)
      saveSession(tokenData.access_token, email)
      setUserEmail(email)
      setIsAuthenticated(true)
      setFeedbackType('success')
      setMessage(mode === 'signup' ? 'Account created and you are signed in.' : 'Signed in successfully.')
      setPassword('')
    } catch (error) {
      setFeedbackType('error')
      setMessage(error instanceof Error ? error.message : 'Unexpected error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    resetSession()
    setFeedbackType('info')
    setMessage('You have been logged out.')
  }

  const changeMode = (nextMode: AuthMode) => {
    setMode(nextMode)
    setMessage('')
  }

  return {
    mode,
    setMode: changeMode,
    email,
    setEmail,
    password,
    setPassword,
    isAuthenticated,
    userEmail,
    loading,
    message,
    feedbackType,
    handleSubmit,
    handleLogout,
  }
}
