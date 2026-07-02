import { useState } from 'react'
import { CreateSessionForm } from './CreateSessionForm'
import { SessionList } from './SessionList'
import type { SessionItem } from '../types/session'

interface SessionsDashboardProps {
  token: string | null
  sessions: SessionItem[]
  loading: boolean
  message: string
  error: string
  onCreateSession: (formData: FormData) => Promise<void>
  onSelectSession: (sessionId: number) => void
}

export function SessionsDashboard({
  token,
  sessions,
  loading,
  message,
  error,
  onCreateSession,
  onSelectSession,
}: SessionsDashboardProps) {
  const [isCreateOpen, setIsCreateOpen] = useState(false)

  return (
    <div className="sessions-page">
      <div className="sessions-page__header">
        <div className="sessions-page__topbar">
          <div>
            <h2>Your sessions</h2>
            <p>Create and manage your interview preparation sessions.</p>
          </div>
          <button type="button" className="primary-btn" onClick={() => setIsCreateOpen(true)}>
            Create session
          </button>
        </div>
      </div>

      {message ? <div className="feedback success">{message}</div> : null}
      {error ? <div className="feedback error">{error}</div> : null}

      {isCreateOpen ? (
        <div className="modal-backdrop" onClick={() => setIsCreateOpen(false)}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()}>
            <div className="modal-card__header">
              <h3>Create new session</h3>
              <button type="button" className="ghost-btn" onClick={() => setIsCreateOpen(false)}>
                Close
              </button>
            </div>
            <CreateSessionForm
              onCreate={async (formData) => {
                await onCreateSession(formData)
                setIsCreateOpen(false)
              }}
              loading={loading}
            />
          </div>
        </div>
      ) : null}

      <SessionList sessions={sessions} loading={loading} token={token} onSelectSession={onSelectSession} />
    </div>
  )
}
