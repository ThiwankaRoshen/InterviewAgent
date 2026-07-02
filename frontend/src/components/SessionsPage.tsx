import { useEffect, useState } from 'react'
import { useSessions } from '../hooks/useSessions'
import { fetchSessionDetail } from '../services/sessionService'
import { SessionsDashboard } from './SessionsDashboard'
import { SessionDetailView } from './SessionDetailView'
import type { SessionDetail } from '../types/session'

interface SessionsPageProps {
  token: string | null
}

export function SessionsPage({ token }: SessionsPageProps) {
  const { sessions, loading, message, error, handleCreateSession } = useSessions(token)
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null)
  const [activeSession, setActiveSession] = useState<SessionDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')

  useEffect(() => {
    if (!selectedSessionId || !token) {
      return
    }

    const loadSessionDetail = async () => {
      setDetailLoading(true)
      setDetailError('')

      try {
        const detail = await fetchSessionDetail(token, selectedSessionId)
        setActiveSession(detail)
      } catch (error) {
        setDetailError(error instanceof Error ? error.message : 'Unable to load session details.')
      } finally {
        setDetailLoading(false)
      }
    }

    void loadSessionDetail()
  }, [selectedSessionId, token])

  if (!token) {
    return null
  }

  if (selectedSessionId) {
    return (
      <SessionDetailView
        session={activeSession}
        loading={detailLoading}
        error={detailError}
        token={token}
        onBack={() => {
          setSelectedSessionId(null)
          setActiveSession(null)
          setDetailError('')
        }}
        onSessionUpdated={(updatedSession) => setActiveSession(updatedSession)}
      />
    )
  }

  return (
    <SessionsDashboard
      token={token}
      sessions={sessions}
      loading={loading}
      message={message}
      error={error}
      onCreateSession={handleCreateSession}
      onSelectSession={(sessionId) => setSelectedSessionId(sessionId)}
    />
  )
}
