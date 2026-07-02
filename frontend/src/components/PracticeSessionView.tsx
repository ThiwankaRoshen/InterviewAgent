import type { StageItem } from '../types/session'
import type { PracticeSession } from '../types/practice'

interface PracticeSessionViewProps {
  stage: StageItem
  practiceSession: PracticeSession
  isLoading: boolean
  onStop: () => void
  onBack: () => void
}

export function PracticeSessionView({
  stage,
  practiceSession,
  isLoading,
  onStop,
  onBack,
}: PracticeSessionViewProps) {
  return (
    <div className="practice-session">
      <div className="practice-session__header">
        <div>
          <h3>{stage.stage_name}</h3>
          <p className="practice-session__subtitle">{stage.stage_description}</p>
        </div>
        <button type="button" className="ghost-btn" onClick={onBack}>
          Back
        </button>
      </div>

      <div className="practice-session__content">
        <div className="practice-session__info">
          <p className="practice-session__info-label">Interview room ready</p>
          <p className="practice-session__info-text">
            You're connected to your practice session. Click the link below to join the video room.
          </p>
        </div>

        <a
          href={practiceSession.roomUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="practice-session__link"
        >
          Join Interview Room
          <span className="practice-session__link-icon">↗</span>
        </a>

        <div className="practice-session__details">
          <div className="practice-session__detail-item">
            <span className="practice-session__detail-label">Room:</span>
            <code className="practice-session__detail-value">{practiceSession.roomUrl.split('/').pop()}</code>
          </div>
          <div className="practice-session__detail-item">
            <span className="practice-session__detail-label">Stage ID:</span>
            <code className="practice-session__detail-value">{practiceSession.stageId}</code>
          </div>
        </div>

        <button
          type="button"
          className="practice-session__stop-btn"
          onClick={() => void onStop()}
          disabled={isLoading}
        >
          {isLoading ? 'Stopping…' : 'Stop Interview'}
        </button>
      </div>
    </div>
  )
}
