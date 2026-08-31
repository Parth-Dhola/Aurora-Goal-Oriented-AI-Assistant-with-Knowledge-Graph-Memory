"""
routes/documents.py — PDF Document Upload & Management API

Endpoints:
  POST   /api/documents/upload  — Upload a PDF document and structure into KG & Obsidian
  GET    /api/documents/        — List all documents for the current user
  GET    /api/documents/{id}    — Get document metadata and generated topic notes
  DELETE /api/documents/{id}    — Delete document, topic chunks, and Obsidian files
"""

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from services.auth_service import get_current_user
from services.document_service import (
    process_and_graph_document,
    list_user_documents,
    get_document_details,
    delete_user_document
)

router = APIRouter()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """
    Upload a PDF document.
    Decomposes the PDF into topic notes for Obsidian and creates nodes/edges in the Knowledge Graph.
    """
    if not file.filename.lower().endswith((".pdf", ".txt")):
        raise HTTPException(
            status_code=400,
            detail="Currently only PDF and TXT documents are supported."
        )

    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        # Process document, create notes, and link into KG
        result = process_and_graph_document(content, file.filename, user["id"])
        return {
            "status": "success",
            "message": f"Successfully structured '{file.filename}' into {result['topics_created']} topic notes.",
            "document": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process document: {str(e)}"
        )


@router.get("/")
async def list_documents(user: dict = Depends(get_current_user)):
    """List all documents uploaded by the authenticated user."""
    docs = list_user_documents(user["id"])
    return {"documents": docs, "total": len(docs)}


@router.get("/{doc_id}")
async def get_document(doc_id: int, user: dict = Depends(get_current_user)):
    """Get details for a specific document including its generated topic notes."""
    doc = get_document_details(doc_id, user["id"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.delete("/{doc_id}")
async def delete_document(doc_id: int, user: dict = Depends(get_current_user)):
    """Delete a document, its database chunks, and local Obsidian notes."""
    success = delete_user_document(doc_id, user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"status": "deleted", "id": doc_id}
