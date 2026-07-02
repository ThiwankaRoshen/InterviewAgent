import type { SessionDetail, SessionItem } from '../types/session'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

async function parseErrorMessage(response: Response): Promise<string> {
  const data = await response.json().catch(() => null)
  return data?.detail || data?.message || 'Request failed. Please try again.'
}

export async function fetchUserSessions(token: string): Promise<SessionItem[]> {
  const response = await fetch(`${API_BASE_URL}/api/sessions`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  return response.json()
}

export async function createSession(token: string, formData: FormData): Promise<SessionItem> {
  const response = await fetch(`${API_BASE_URL}/api/sessions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  return response.json()
}

export async function fetchSessionDetail(token: string, sessionId: number): Promise<SessionDetail> {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  return response.json()
}
