import type { SessionItem } from '../types/session'

interface SessionListProps {
  sessions: SessionItem[]
  loading: boolean
}

export function SessionList({ sessions, loading }: SessionListProps) {
  if (loading) {
    return <p className="empty-state">Loading your sessions…</p>
  }

  if (!sessions.length) {
    return <p className="empty-state">No sessions yet. Create your first one to begin.</p>
  }

  return (
    <div className="session-list">
      {sessions.map((session) => (
        <article key={session.id} className="session-card">
          <div className="session-card__top">
            <h3>{session.job_description}</h3>
            <span>{new Date(session.date_created).toLocaleDateString()}</span>
          </div>
          <p className="session-card__meta">Company: {session.company_info}</p>
          <p className="session-card__meta">Notes: {session.additional_info}</p>
        </article>
      ))}
    </div>
  )
}
