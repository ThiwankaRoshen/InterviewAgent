export interface SessionItem {
  id: number
  date_created: string
  job_description: string
  company_info: string
  additional_info: string
}

export interface StageItem {
  stage_order: number
  stage_name: string
  stage_description: string
}

export interface SessionDetail extends SessionItem {
  stages: StageItem[]
}

export interface InterviewPlanResponse {
  session_id: number
  stages: StageItem[]
}
