interface AuthenticatedStateProps {
  userEmail: string
  onLogout: () => void
}

export function AuthenticatedState({ userEmail, onLogout }: AuthenticatedStateProps) {
  return (
    <div className="auth-card__success">
      <p>
        You are signed in as <strong>{userEmail}</strong>.
      </p>
      <button type="button" className="primary-btn" onClick={onLogout}>
        Log out
      </button>
    </div>
  )
}
