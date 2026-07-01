from typing import Annotated
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from schemas import SessionResponse, UserUpdate, UserCreate, UserPrivate, UserPublic, Token
import models

from datetime import timedelta
from fastapi.security import OAuth2PasswordRequestForm
from auth import CurrentUser, create_access_token, hash_password, verify_password
from database import DBSession
from server.crud import get_user_cvs
from server.cv_utils import delete_cv_file
from settings import settings

router = APIRouter()


@router.post("", response_model=UserPrivate, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: DBSession):
    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == user.email.lower()
        )
    )
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A User Exist with this email.",
        )
    new_user = models.User(
        email=user.email.lower(),
        password_hash=hash_password(user.password),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: DBSession
):
    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == form_data.username.lower()
        )
    )
    user = result.scalars().first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect Email or Password.",
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserPrivate)
async def get_current_user(current_user: CurrentUser):
    return current_user


@router.patch(
    "/{user_id}", response_model=UserUpdate, status_code=status.HTTP_201_CREATED
)
async def update_user_patch(
    user_id: int, user: UserUpdate, current_user: CurrentUser, db: DBSession
):
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not Authorized to update this profile.",
        )

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    existing_user = result.scalars().first()
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not Exist.",
        )
    if user.email and existing_user.email != user.email.lower():
        result = (
                await db.execute(
                    select(models.User).where(
                        func.lower(models.User.email) == user.email.lower(),
                        models.User.id != user_id,
                    )
                )
            ).scalars().first()
        
        if result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A User Exist with this email.",
            )
 
    if user.email is not None:
        existing_user.email = user.email

    await db.commit()
    await db.refresh(existing_user)
    return existing_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, current_user: CurrentUser, db: DBSession):
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not Authorized to delete this profile.",
        )
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    existing_user = result.scalars().first()
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not Exist.",
        ) 
        
    cv_paths = await get_user_cvs(db, user_id)
    for cv_path in cv_paths:
        delete_cv_file(cv_path)

    await db.delete(existing_user)
    await db.commit()

@router.get("/{user_id}", response_model=UserPublic)
async def get_user(user_id: int, db: DBSession):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User Doesn't Exist."
        )
    return user


@router.get("/{user_id}/sessions", response_model=list[SessionResponse])
async def get_user_sessions(user_id: int, db: DBSession):
    results = await get_user_sessions(db, user_id)
    return results
