import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_services, get_session
from app.db.models import Document
from app.schemas.api import DocumentOut
from app.services.container import Services
from app.services.ingestion import DuplicateDocumentError, IngestionError

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
async def list_documents(session: AsyncSession = Depends(get_session)) -> list[Document]:
    result = await session.scalars(select(Document).order_by(Document.created_at.desc()))
    return list(result)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile, services: Services = Depends(get_services)) -> Document:
    filename = (file.filename or "document.pdf").rsplit("/", 1)[-1]
    if not filename.lower().endswith(".pdf") and file.content_type != "application/pdf":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF files are supported")

    limit = services.settings.max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"File exceeds the {services.settings.max_upload_mb} MB limit",
        )
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File is not a valid PDF")

    try:
        return await services.ingestion.ingest_pdf(filename, data)
    except DuplicateDocumentError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except IngestionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, services: Services = Depends(get_services)):
    if not await services.ingestion.delete_document(document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
