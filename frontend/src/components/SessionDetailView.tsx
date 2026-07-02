import { useEffect, useRef, useState } from 'react'
import { generateSessionStages } from '../services/sessionService'
import type { SessionDetail, StageItem } from '../types/session'

interface SessionDetailViewProps {
  session: SessionDetail | null
  loading: boolean
  error: string
  token: string | null
  onBack: () => void
  onSessionUpdated?: (session: SessionDetail) => void
}

interface ProgressMessage {
  type: 'connected' | 'progress' | 'complete' | 'error'
  step?: string
  progress?: number
  detail?: string
  error?: string
  stage_count?: number
}

function buildWebSocketUrl(sessionId: number) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000')
    .replace(/^http:/, 'ws:')
    .replace(/^https:/, 'wss:')

  return `${baseUrl}/ws/session/${sessionId}`
}

export function SessionDetailView({
  session,
  loading,
  error,
  token,
  onBack,
  onSessionUpdated,
}: SessionDetailViewProps) {
  const [isGenerating, setIsGenerating] = useState(false)
  const [generationError, setGenerationError] = useState('')
  const [progressStep, setProgressStep] = useState('')
  const [progressPercent, setProgressPercent] = useState(0)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    return () => {
      if (socketRef.current) {
        socketRef.current.close()
        socketRef.current = null
      }
    }
  }, [])

  const closeSocket = () => {
    if (socketRef.current) {
      socketRef.current.close()
      socketRef.current = null
    }
  }

  const handleGenerateStages = async () => {
    if (!token || !session) {
      return
    }

    setIsGenerating(true)
    setGenerationError('')
    setProgressStep('Connecting to progress stream…')
    setProgressPercent(0)
    closeSocket()

    const socket = new WebSocket(buildWebSocketUrl(session.id))
    socketRef.current = socket

    socket.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data) as ProgressMessage

        if (payload.type === 'connected') {
          setProgressStep('Starting stage generation…')
          return
        }

        if (payload.type === 'progress') {
          setProgressStep(payload.step || 'Working…')
          setProgressPercent(payload.progress ?? 0)
          return
        }

        if (payload.type === 'complete') {
          setProgressStep('Stages are ready')
          setProgressPercent(100)
          setTimeout(() => {
            closeSocket()
          }, 200)
        }

        if (payload.type === 'error') {
          setGenerationError(payload.detail || payload.error || 'Stage generation failed.')
          setProgressStep('Generation failed')
          setProgressPercent(0)
          closeSocket()
        }
      } catch {
        setGenerationError('Received an invalid progress update from the server.')
      }
    })

    socket.addEventListener('error', () => {
      setGenerationError('Unable to connect to the live progress stream.')
      setProgressStep('Connection issue')
      setProgressPercent(0)
      closeSocket()
    })

    try {
      const result = await generateSessionStages(token, session.id)
      const updatedSession: SessionDetail = {
        ...session,
        stages: result.stages as StageItem[],
      }
      onSessionUpdated?.(updatedSession)
      setProgressStep('Stages are ready')
      setProgressPercent(100)
    } catch (error) {
      setGenerationError(error instanceof Error ? error.message : 'Unable to generate stages.')
      setProgressStep('Generation failed')
      setProgressPercent(0)
    } finally {
      setIsGenerating(false)
      setTimeout(() => {
        closeSocket()
      }, 300)
    }
  }

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

      {generationError ? <div className="feedback error">{generationError}</div> : null}

      {isGenerating ? (
        <div className="generation-progress">
          <div className="generation-progress__header">
            <strong>{progressStep || 'Generating interview stages…'}</strong>
            <span>{progressPercent}%</span>
          </div>
          <div className="generation-progress__bar" aria-hidden="true">
            <div className="generation-progress__fill" style={{ width: `${progressPercent}%` }} />
          </div>
        </div>
      ) : null}

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
        <button type="button" className="primary-btn" onClick={() => void handleGenerateStages()} disabled={isGenerating}>
          {isGenerating ? 'Generating…' : 'Generate stages'}
        </button>
      )}

      {session.stages && session.stages.length > 0 ? (
        <button type="button" className="primary-btn" onClick={() => void handleGenerateStages()} disabled={isGenerating}>
          {isGenerating ? 'Generating…' : 'Regenerate stages'}
        </button>
      ) : null}
    </div>
  )
}
