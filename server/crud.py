from datetime import datetime, UTC
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
import models
import schemas
from cv_utils import save_cv_file
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def get_session(db: AsyncSession, session_id: int) -> models.Session:
    session = await db.execute(
        select(models.Session).options(selectinload(models.Session.stages)).where(models.Session.id == session_id)
    )

    session = session.scalars().first()

    return session


async def get_sessions(db: AsyncSession, user_id: int) -> list[models.Session]:
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
    cv: UploadFile,
    db: AsyncSession, 
    session_data: schemas.SessionCreate,
    user_id: int
) -> models.Session:

    cv_file_name = await save_cv_file(cv)

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

async def get_stage(
    db: AsyncSession,
    stage_id: int,
) -> models.Stage | None:

    result = await db.execute(
        select(models.Stage).where(
            models.Stage.id == stage_id
        )
    )

    return result.scalar_one_or_none()

async def create_practice_attempt(
    db: AsyncSession,
    stage_id: int,
    room_url: str,
    token: str,
    status: str = "STARTED",
) -> models.PracticeAttempt:

    practice = models.PracticeAttempt(
        stage_id=stage_id,
        room_url=room_url,
        token=token,
        status=status,
    )

    db.add(practice)
    await db.commit()
    await db.refresh(practice)

    return practice

async def get_practice_attempt(
    db: AsyncSession,
    practice_attempt_id: int,
) -> models.PracticeAttempt | None:

    result = await db.execute(
        select(models.PracticeAttempt).where(
            models.PracticeAttempt.id == practice_attempt_id
        )
    )

    return result.scalar_one_or_none()

async def get_practice_attempts(
    db: AsyncSession,
    stage_id: int,
) -> models.PracticeAttempt | None:

    results = await db.execute(
        select(models.PracticeAttempt).where(
            models.PracticeAttempt.stage_id == stage_id
        )
    )

    return results.scalars().all()

async def stop_practice_attempt(
    db: AsyncSession,
    practice_attempt_id: int,
) -> models.PracticeAttempt | None:

    practice = await get_practice_attempt(db, practice_attempt_id)

    if practice is None:
        return None

    practice.status = "STOPPED"

    await db.commit()
    await db.refresh(practice)

    return practice

async def practice_attempt_owned_by(
    db: AsyncSession,
    practice_attempt_id: int,
    user_id: int,
) -> bool:

    result = await db.execute(
        select(models.PracticeAttempt)
        .join(models.Stage)
        .join(models.Session)
        .where(
            models.PracticeAttempt.id == practice_attempt_id,
            models.Session.user_id == user_id,
        )
    )

    return result.scalar_one_or_none() is not None

async def stage_owned_by(
    db: AsyncSession,
    stage_id: int,
    user_id: int,
) -> bool:

    result = await db.execute(
        select(models.Stage)
        .join(models.Session)
        .where(
            models.Stage.id == stage_id,
            models.Session.user_id == user_id,
        )
    )

    return result.scalar_one_or_none() is not None