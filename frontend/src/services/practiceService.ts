import type { StartPracticeResponse } from '../types/practice'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

async function parseErrorMessage(response: Response): Promise<string> {
  const data = await response.json().catch(() => null)
  return data?.detail || data?.message || 'Request failed. Please try again.'
}

export async function startPracticeSession(
  token: string,
  stageId: number,
  practiceSessionId: number,
): Promise<StartPracticeResponse> {
  const response = await fetch(`${API_BASE_URL}/api/practices/start`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      stage_id: stageId,
      practice_session_id: practiceSessionId,
    }),
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  return response.json()
}

export async function stopPracticeSession(token: string, roomUrl: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/practices/stop`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      room_url: roomUrl,
    }),
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
}

export async function createPracticeSession(token: string, sessionId: number): Promise<number> {
  const response = await fetch(`${API_BASE_URL}/api/practices/${sessionId}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  const data = await response.json()
  return data.practice_session_id
}
