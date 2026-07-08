export interface StartPracticeResponse {
  practice_attempt_id?: number | null
  id?: number | null
  practice_session_id?: number | null
  room_url: string
  token: string
  status: string
  md_results_path: string
  pdf_results_path: string
}

export interface PracticeSession {
  stageId: number
  practiceAttemptId: number | null
  roomUrl: string
  token: string
  status: string
  mdResultsPath: string
  pdfResultsPath: string
}
