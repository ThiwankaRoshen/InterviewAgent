import { useState } from 'react'
import { startPracticeSession, stopPracticeSession } from '../services/practiceService'
import type { PracticeSession } from '../types/practice'

interface UsePracticeSessionOptions {
  token: string | null
  sessionId: number
}

export function usePracticeSession({ token }: UsePracticeSessionOptions) {
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
      const response = await startPracticeSession(token, stageId)
      const practiceAttemptId = response.practice_attempt_id ?? response.id ?? response.practice_session_id

      if (!practiceAttemptId) {
        setError('The server did not return a practice attempt ID.')
        return false
      }

      setPracticeSessions({
        stageId,
        practiceAttemptId,
        roomUrl: response.room_url,
        token: response.token,
        status: response.status,
        mdResultsPath: response.md_results_path,
        pdfResultsPath: response.pdf_results_path,
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
      await stopPracticeSession(token, practiceSessions.practiceAttemptId)
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
