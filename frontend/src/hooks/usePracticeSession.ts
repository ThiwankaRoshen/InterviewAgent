import { useState } from 'react'
import { createPracticeSession, startPracticeSession, stopPracticeSession } from '../services/practiceService'
import type { PracticeSession } from '../types/practice'

interface UsePracticeSessionOptions {
  token: string | null
  sessionId: number
}

export function usePracticeSession({ token, sessionId }: UsePracticeSessionOptions) {
  const [practiceSessions, setPracticeSessions] = useState<PracticeSession | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const startPractice = async (stageId: number) => {
    if (!token) {
      setError('Authentication required')
      return false
    }

    setIsLoading(true)
    setError('')

    try {
      const practiceSessionId = await createPracticeSession(token, sessionId)
      const response = await startPracticeSession(token, stageId, practiceSessionId)

      setPracticeSessions({
        stageId: response.stage_id,
        practiceSessionId: response.practice_session_id,
        roomUrl: response.room_url,
        token: response.token,
      })

      return true
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to start practice session'
      setError(errorMessage)
      return false
    } finally {
      setIsLoading(false)
    }
  }

  const stopPractice = async () => {
    if (!token || !practiceSessions) {
      return false
    }

    setIsLoading(true)
    setError('')

    try {
      await stopPracticeSession(token, practiceSessions.roomUrl)
      setPracticeSessions(null)
      return true
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to stop practice session'
      setError(errorMessage)
      return false
    } finally {
      setIsLoading(false)
    }
  }

  const clearSession = () => {
    setPracticeSessions(null)
    setError('')
  }

  return {
    practiceSessions,
    isLoading,
    error,
    startPractice,
    stopPractice,
    clearSession,
  }
}
