import type { SessionItem } from '../types/session'

interface SessionListProps {
  sessions: SessionItem[]
  loading: boolean
  token: string | null
  onSelectSession: (sessionId: number) => void
}

function truncate(text: string, maxLength = 90) {
  if (!text) {
    return 'No details provided.'
  }

  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text
}

export function SessionList({ sessions, loading, token, onSelectSession }: SessionListProps) {
  if (loading) {
    return <p className="empty-state">Loading your sessions…</p>
  }

  if (!sessions.length) {
    return <p className="empty-state">No sessions yet. Create your first one to begin.</p>
  }

  return (
    <>
      <div className="session-list">
        {sessions.map((session) => (
          <button
            key={session.id}
            type="button"
            className="session-card session-card--button"
            onClick={() => {
              if (token) {
                onSelectSession(session.id)
              }
            }}
          >
            <div className="session-card__top">
              <h3>Session {session.id}</h3>
              <span>{new Date(session.date_created).toLocaleDateString()}</span>
            </div>
            <p className="session-card__meta">{truncate(session.job_description)}</p>
            <p className="session-card__meta">{truncate(session.company_info)}</p>
            <p className="session-card__meta">{truncate(session.additional_info)}</p>
          </button>
        ))}
      </div>
    </>
  )
}
