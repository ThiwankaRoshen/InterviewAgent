import uuid
from pathlib import Path
from fastapi import UploadFile, HTTPException

from settings import settings

CV_FILES_DIR = Path("media/cv_files")

ALLOWED_CV_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


async def save_cv_file(file: UploadFile) -> str:
    if file.content_type not in ALLOWED_CV_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF, DOC, and DOCX files are allowed.",
        )

    content = await file.read()

    if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum size is 5MB.",
        )

    extension = ALLOWED_CV_CONTENT_TYPES[file.content_type]
    filename = f"{uuid.uuid4().hex}{extension}"
    filepath = CV_FILES_DIR / filename

    CV_FILES_DIR.mkdir(parents=True, exist_ok=True)

    with open(filepath, "wb") as f:
        f.write(content)

    return filename


def delete_cv_file(filename: str | None) -> None:
    if filename is None:
        return None

    filepath = CV_FILES_DIR / filename
    if filepath.exists():
        filepath.unlink()