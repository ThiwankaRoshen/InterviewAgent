from datetime import datetime, UTC
from pathlib import Path

# from langchain_mistralai import ChatMistralAI
# from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from interview_evaluation_utils import markdown_to_pdf
from settings import settings

async def trigger_stage_evaluation_pipeline(active_session):
    """
    Evaluate interview answers and generate a markdown report + PDF.
    """

    # llm = ChatMistralAI(
    #     model=settings.MISTRAL_MODEL,
    #     temperature=0,
    #     max_retries=2,
    #     mistral_api_key=settings.MISTRAL_API_KEY
    # )
    

    # Inside your class setup:
    # llm = ChatGoogleGenerativeAI(
    #     model="gemini-2.5-flash",  # Or "gemini-3.5-flash" depending on your preferred version
    #     temperature=0,
    #     max_retries=2,
    #     google_api_key=settings.GOOGLE_API_KEY
    # )
    llm = ChatOpenAI(
            base_url=settings.BASE_URL_INTERVIEW_GEN,
            model=settings.MODEL_INTERVIEW_GEN,
            temperature=0,
            api_key=settings.GITHUB_TOKEN_INTERVIEW_GEN,
        ) 

    interview_text = ""

    for answer in active_session.answers_log:

        interview_text += f"""
### Question:
{answer["question_text"]}

**Expected Behaviour**:
{answer["expected_behavior"]}

**Candidate behaviour**:
{answer["behaviour"]}

**Candidate Answer**:
{answer["answer_text"]}

---------------------------------------
"""

    prompt = f"""
You are a senior interview evaluator.

Evaluate the candidate's {active_session.stage_name} interview stage.
About Interview Stage:
{active_session.stage_description}

---

**CRITICAL FORMATTING RULES (Follow strictly)**:
- Use **ONLY Markdown** (no HTML, no raw JSON).
- Separate every major section with a horizontal rule: `---`.
- Use **bold** (`**text**`) for: scores, key traits, section titles within paragraphs, and the final verdict.
- Use *italic* (`*text*`) for subtle emphasis or sub‑titles.
- Use **nested bullet lists** (`- ` and `  - `) – never write long paragraphs without breaks.
- Use **blockquotes** (`> `) sparingly for 1–2 critical "Key Insight" or "Red Flag" callouts per section.
- For the Question-by-Question feedback, strictly follow this exact sub‑structure:

  ### Question X: [Brief Topic or Question Title]
  - **Score**: [X/10 or X/100]
  - **Strengths**:
    - [Specific point 1]
    - [Specific point 2]
  - **Improvements / Areas for Growth**:
    - [Specific point 1]
  - **Detailed Notes**: [Write 1–2 concise, constructive sentences referencing the candidate's exact words.]

---

**REPORT STRUCTURE (Must follow this order)**:

1. # Interview Evaluation Report

2. ---

3. ## Executive Summary
   - Write 2–3 sentences summarizing the candidate's overall performance, key takeaway, and whether they seem aligned with the role.

4. ## Overall Score
   - Present the final score prominently: **Score: [XX]/100**
   - Write a brief rationale (2–3 sentences) justifying this score based on the answers.

5. ## Key Strengths
   - Bulleted list (with nested sub‑points if needed) of the candidate's top 3–5 strengths.
   - Reference specific answers or behaviors from the interview.

6. ## Areas for Development
   - Bulleted list (with nested sub‑points) of the candidate's top 3–5 weaknesses or gaps.
   - Suggest actionable improvements where possible.

7. ## Question-by-Question Breakdown
   - Use the strict sub‑structure defined above for **every** question in the interview log.
   - Be specific – refer to what the candidate actually said.

8. ## Communication & Professionalism Assessment
   - Assess clarity, confidence, tone, pacing, and overall presence.
   - Use a mix of short paragraphs and bullet points for readability.

9. ## Final Recommendation & Verdict
   - Start with a bolded **Pass** / **Fail** / **On Hold**.
   - Add a detailed justification (3–5 sentences) tying back to the score, strengths, and weaknesses.

---

**Interview Data to Evaluate**:

{interview_text}

---------------------------------------

**EXAMPLE OF EXPECTED OUTPUT STRUCTURE (follow this exactly)**:

# Interview Evaluation Report

---

## Executive Summary
[Write 2-3 sentences summarizing overall performance.]

---

## Overall Score
**Score: [XX]/100**
[Rationale in 2-3 sentences.]

---

## Key Strengths
- Strength 1
  - Sub-point or specific example
- Strength 2
  - Sub-point

---

## Areas for Development
- Weakness 1
  - Sub-point
- Weakness 2
  - Sub-point

---

## Question-by-Question Breakdown

### Question 1: [Title]
- **Score**: [X/10]
- **Strengths**:
  - Point
- **Improvements**:
  - Point
- **Detailed Notes**: [Sentence]

---

### Question 2: [Title]
... (repeat for all questions)

---

## Communication & Professionalism Assessment
[Use bullets and paragraphs.]

---

## Final Recommendation & Verdict
**Pass** / **Fail** / **On Hold**
[Detailed justification.]

"""

    response = await llm.ainvoke(prompt)

    markdown_report = response.content

    reports_dir = Path("media/reports")
    reports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    md_path = reports_dir / f"practice_{active_session.practice_attempt_id}.md"
    pdf_path = reports_dir / f"practice_{active_session.practice_attempt_id}.pdf"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_report)

    markdown_to_pdf(
        markdown_report,
        str(pdf_path),
    )

    print(f"Markdown saved to {md_path}")
    print(f"PDF saved to {pdf_path}")