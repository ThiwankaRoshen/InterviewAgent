import { useEffect, useState } from 'react'
import { createSession, fetchUserSessions } from '../services/sessionService'
import type { SessionItem } from '../types/session'

export function useSessions(token: string | null) {
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const loadSessions = async () => {
    if (!token) {
      return
    }

    setLoading(true)
    setError('')

    try {
      const data = await fetchUserSessions(token)
      setSessions(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load sessions.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadSessions()
  }, [token])

  const handleCreateSession = async (formData: FormData) => {
    if (!token) {
      return
    }

    setLoading(true)
    setError('')
    setMessage('')

    try {
      const created = await createSession(token, formData)
      setSessions((current) => [created, ...current])
      setMessage('Session created successfully.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create session.')
    } finally {
      setLoading(false)
    }
  }

  return {
    sessions,
    loading,
    message,
    error,
    loadSessions,
    handleCreateSession,
  }
}
