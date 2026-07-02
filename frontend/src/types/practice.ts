export interface StartPracticeResponse {
  practice_session_id: number
  stage_id: number
  room_url: string
  token: string
}

export interface PracticeSession {
  stageId: number
  practiceSessionId: number
  roomUrl: string
  token: string
}
