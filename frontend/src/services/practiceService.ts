import type { StartPracticeResponse } from '../types/practice'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

async function parseErrorMessage(response: Response): Promise<string> {
  const data = await response.json().catch(() => null)
  return data?.detail || data?.message || 'Request failed. Please try again.'
}

export async function startPracticeSession(token: string, stageId: number): Promise<StartPracticeResponse> {
  const response = await fetch(`${API_BASE_URL}/api/practices/${stageId}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  return response.json()
}

export async function stopPracticeSession(token: string, practiceAttemptId: number | null): Promise<void> {
  if (!practiceAttemptId) {
    throw new Error('No practice attempt ID available to stop the session.')
  }

  const response = await fetch(`${API_BASE_URL}/api/practices/stop/${practiceAttemptId}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
}
