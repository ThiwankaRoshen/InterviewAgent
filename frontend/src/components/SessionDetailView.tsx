import type { SessionDetail } from '../types/session'

interface SessionDetailViewProps {
  session: SessionDetail | null
  loading: boolean
  error: string
  onBack: () => void
}

export function SessionDetailView({ session, loading, error, onBack }: SessionDetailViewProps) {
  if (loading) {
    return <p className="empty-state">Loading session details…</p>
  }

  if (error) {
    return <div className="feedback error">{error}</div>
  }

  if (!session) {
    return null
  }

  return (
    <div className="detail-panel">
      <div className="detail-panel__header">
        <h3>Session {session.id}</h3>
        <button type="button" className="ghost-btn" onClick={onBack}>
          Back to sessions
        </button>
      </div>

      <p className="detail-panel__text">{session.job_description}</p>
      <p className="detail-panel__text">{session.company_info}</p>
      <p className="detail-panel__text">{session.additional_info}</p>

      {session.stages && session.stages.length > 0 ? (
        <div className="stage-list">
          {session.stages.map((stage) => (
            <div key={`${stage.stage_order}-${stage.stage_name}`} className="stage-item">
              <h4>{stage.stage_name}</h4>
              <p>{stage.stage_description}</p>
            </div>
          ))}
        </div>
      ) : (
        <button type="button" className="primary-btn">
          Start generate stages
        </button>
      )}
    </div>
  )
}
