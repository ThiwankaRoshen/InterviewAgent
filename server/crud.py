from datetime import datetime, UTC
from sqlalchemy import func, select
import models
import schemas
from cv_utils import save_cv_file
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def get_session(db: AsyncSession, session_id: int) -> models.Session:
    session = await db.execute(
        select(models.Session).where(models.Session.id == session_id)
    )

    session = session.scalars().first()

    return session


async def get_user_sessions(db: AsyncSession, user_id: int) -> list[models.Session]:
    results = await db.execute(
        select(models.Session).where(models.Session.user_id == user_id)
    )
    results = results.scalars().all()

    return results


async def get_user_cvs(db: AsyncSession, user_id: int) -> list[str]:
    results = await db.execute(
        select(models.Session).where(models.Session.user_id == user_id)
    )
    results = results.scalars().all()

    cv_paths = [result.cv_file_path for result in results.scalars().all()]

    return cv_paths


async def create_session(
    db: AsyncSession, session_data: schemas.SessionCreate, user_id: int
) -> models.Session:

    cv_file_name = save_cv_file(session_data.cv)

    session = models.Session(
        cv_file_name=cv_file_name,
        job_description=session_data.job_description,
        company_info=session_data.company_info,
        additional_info=session_data.additional_info,
        user_id=user_id,
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)

    return session


async def create_interview_stages(
    db: AsyncSession, session_id: int, generated_stages: list[schemas.StageBase]
) -> list[models.Stage]:
    stages = []

    for stage_data in generated_stages:
        stage = models.Stage(
            stage_order=stage_data.stage_order,
            stage_name=stage_data.stage_name,
            stage_description=stage_data.stage_description,
            interviewer_persona=stage_data.interviewer_persona,
            questions_and_answers=stage_data.questions_and_answers,
            session_id=session_id,
        )
        db.add(stage)
        stages.append(stage)

    await db.commit()

    for stage in stages:
        await db.refresh(stage)

    return stages


async def get_interview_stages(
    db: AsyncSession,
    session_id: int,
) -> list[models.Stage]:

    result = await db.execute(
        select(models.Stage)
        .where(models.Stage.session_id == session_id)
        .order_by(models.Stage.stage_order)
    )
    stages = result.scalars().all()

    return stages


async def get_interview_stage(
    db: AsyncSession,
    stage_order: int,
    session_id: int,
) -> models.Stage:

    result = await db.execute(
        select(models.Stage).where(
            models.Stage.session_id == session_id,
            models.Stage.stage_order == stage_order,
        )
    )
    stage = result.scalars().first()

    return stage


def initialize_practice_run(
    db: AsyncSession, session_id: int
) -> tuple[models.PracticeSession, models.PracticeStage]:
    """
    Creates both the active run tracking metadata rows in one transaction.
    """
    # 1. Start the root Practice Session
    practice_session = models.PracticeSession(
        session_id=session_id, created_at=datetime.now(UTC)
    )
    db.add(practice_session)
    db.flush()  # Flushes to get db_practice_session.id before committing

    # 2. Start the tracking wrapper for this stage run
    practice_stage = models.PracticeStage(practice_session_id=practice_session.id)
    db.add(practice_stage)

    db.commit()
    db.refresh(practice_session)
    db.refresh(practice_stage)

    return practice_session, practice_stage


def record_live_answer(
    db: AsyncSession, practice_stage_id: int, answer_data: schemas.AnswerCreate
) -> models.Answer:
    """
    Invoked dynamically when Pipecat triggers an update tool callback after processing an exchange.
    """
    answer = models.Answer(
        practice_stage_id=practice_stage_id,
        question_order=answer_data.question_order,
        question_text=answer_data.question_text,
        behaviour=answer_data.behaviour,
        answer_text=answer_data.answer_text,
    )
    db.add(answer)
    db.commit()
    db.refresh(answer)
    return answer


async def update_session_feedback(
    db: AsyncSession, session_id: int, feedback_data: schemas.SessionFeedbackUpdate
) -> models.Session | None:
    """
    Saves the iteration instructions into the parent session row.
    """
    session = await db.execute(
        select(models.Session).where(models.Session.id == session_id)
    )

    session = session.scalars().first()
    if not session:
        return None

    session.feedback = feedback_data.feedback

    db.commit()
    db.refresh(session)
    return session


async def get_practice_runs_count(
    db: AsyncSession,
    session_id: int,
) -> int:
    """
    Count previous practice runs for an interview session.
    """
    stmt = select(func.count(models.PracticeSession.id)).where(
        models.PracticeSession.session_id == session_id
    )

    result = await db.execute(stmt)
    return result.scalar_one()
