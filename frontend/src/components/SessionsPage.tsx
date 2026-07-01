import { useSessions } from '../hooks/useSessions'
import { CreateSessionForm } from './CreateSessionForm'
import { SessionList } from './SessionList'

interface SessionsPageProps {
  token: string | null
}

export function SessionsPage({ token }: SessionsPageProps) {
  const { sessions, loading, message, error, handleCreateSession } = useSessions(token)

  if (!token) {
    return null
  }

  return (
    <div className="sessions-page">
      <div className="sessions-page__header">
        <h2>Your sessions</h2>
        <p>Create and manage your interview preparation sessions.</p>
      </div>

      {message ? <div className="feedback success">{message}</div> : null}
      {error ? <div className="feedback error">{error}</div> : null}

      <CreateSessionForm onCreate={handleCreateSession} loading={loading} />
      <SessionList sessions={sessions} loading={loading} />
    </div>
  )
}
