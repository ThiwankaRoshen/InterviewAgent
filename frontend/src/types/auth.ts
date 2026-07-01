export type AuthMode = 'login' | 'signup'
export type FeedbackType = 'success' | 'error' | 'info'

export interface UserProfile {
  id: number
  email: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}
