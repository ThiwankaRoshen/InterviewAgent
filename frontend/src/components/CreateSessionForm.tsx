import { useState, type FormEvent } from 'react'

interface CreateSessionFormProps {
  onCreate: (formData: FormData) => Promise<void>
  loading: boolean
}

export function CreateSessionForm({ onCreate, loading }: CreateSessionFormProps) {
  const [jobDescription, setJobDescription] = useState('')
  const [companyInfo, setCompanyInfo] = useState('')
  const [additionalInfo, setAdditionalInfo] = useState('')
  const [cvFile, setCvFile] = useState<File | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (!cvFile) {
      return
    }

    const formData = new FormData()
    formData.append('cv', cvFile)
    formData.append('job_description', jobDescription)
    formData.append('company_info', companyInfo)
    formData.append('additional_info', additionalInfo)

    await onCreate(formData)

    setJobDescription('')
    setCompanyInfo('')
    setAdditionalInfo('')
    setCvFile(null)
  }

  return (
    <form className="create-session-form" onSubmit={handleSubmit}>
      <label className="field">
        <span>CV File</span>
        <input type="file" accept=".pdf,.doc,.docx" onChange={(event) => setCvFile(event.target.files?.[0] || null)} />
      </label>

      <label className="field">
        <span>Job Description</span>
        <textarea value={jobDescription} onChange={(event) => setJobDescription(event.target.value)} rows={3} />
      </label>

      <label className="field">
        <span>Company Info</span>
        <textarea value={companyInfo} onChange={(event) => setCompanyInfo(event.target.value)} rows={3} />
      </label>

      <label className="field">
        <span>Additional Info</span>
        <textarea value={additionalInfo} onChange={(event) => setAdditionalInfo(event.target.value)} rows={3} />
      </label>

      <button type="submit" className="primary-btn" disabled={loading}>
        {loading ? 'Creating…' : 'Create session'}
      </button>
    </form>
  )
}
