from sqlalchemy import select

import models  
import schemas
from server.cv_utils import save_cv_file
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
 
async def get_session(db: AsyncSession, session_id: int) -> models.Session:
    session = await db.execute(
        select(models.Session)
        .where(models.Session.id == session_id)
    ) 
    
    return session

async def create_session(
    db: AsyncSession, 
    session_data: schemas.SessionCreate, 
    user_id: int) -> models.Session:
    
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
    db: AsyncSession, 
    session_id: int, 
    generated_stages: list[schemas.StageBase]
) -> list[models.Stage]:
    db_stages = []
    
    for stage_data in generated_stages:
        db_stage = models.Stage(
            stage_order=stage_data.stage_order,
            stage_name=stage_data.stage_name,
            stage_description=stage_data.stage_description,
            interviewer_persona=stage_data.interviewer_persona,
            questions_and_answers=stage_data.questions_and_answers,
            session_id=session_id
        )
        db.add(db_stage)
        db_stages.append(db_stage)
    
    await db.commit()
    
    for stage in db_stages:
        await db.refresh(stage)
        
    return db_stages

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
        select(models.Stage)
        .where(models.Stage.session_id == session_id,
               models.Stage.stage_order == stage_order)
    )
    stage = result.scalars().first()
        
    return stage



def initialize_practice_run(
    db: AsyncSession,
    session_id: int) -> tuple[models.PracticeSession, models.PracticeStage]:
    """
    Creates both the active run tracking metadata rows in one transaction.
    """
    # 1. Start the root Practice Session
    db_practice_session = models.PracticeSession(
        session_id=session_id,
        created_at=datetime.now(UTC)
    )
    db.add(db_practice_session)
    db.flush()  # Flushes to get db_practice_session.id before committing

    # 2. Start the tracking wrapper for this stage run
    db_practice_stage = models.PracticeStage(
        practice_session_id=db_practice_session.id
    )
    db.add(db_practice_stage)
    
    db.commit()
    db.refresh(db_practice_session)
    db.refresh(db_practice_stage)
    
    return db_practice_session, db_practice_stage


def record_live_answer(
    db: AsyncSession, 
    practice_stage_id: int,
    answer_data: schemas.AnswerCreate) -> models.Answer:
    """
    Invoked dynamically when Pipecat triggers an update tool callback after processing an exchange.
    """
    db_answer = models.Answer(
        practice_stage_id=practice_stage_id,
        question_order=answer_data.question_order,
        question_text=answer_data.question_text,
        behaviour=answer_data.behaviour,
        answer_text=answer_data.answer_text
    )
    db.add(db_answer)
    db.commit()
    db.refresh(db_answer)
    return db_answer



def update_session_feedback(
    db: AsyncSession, 
    session_id: int, 
    feedback_data: schemas.SessionFeedbackUpdate
) -> models.Session | None:
    """
    Saves the iteration instructions into the parent session row.
    """
    db_session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not db_session:
        return None
        
    db_session.feedback = feedback_data.feedback
    
    db.commit()
    db.refresh(db_session)
    return db_session


def get_practice_runs_count(db: AsyncSession, session_id: int) -> int:
    """
    Helper to count previous attempts to see structural history progress.
    """
    return db.query(func.count(models.PracticeSession.id)).filter(
        models.PracticeSession.session_id == session_id
    ).scalar() or 0