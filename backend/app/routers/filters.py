from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import KeywordFilter
from app.schemas import KeywordFilterCreate, KeywordFilterOut
from app.security import verify_jwt_token

router = APIRouter(prefix="/filters", tags=["Keyword Filters"])

@router.get("", response_model=List[KeywordFilterOut])
def list_keyword_filters(
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Lists all active global keyword filters."""
    return db.query(KeywordFilter).order_by(KeywordFilter.created_at.desc()).all()

@router.post("", response_model=KeywordFilterOut, status_code=status.HTTP_201_CREATED)
def create_keyword_filter(
    filter_req: KeywordFilterCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Creates a new global keyword ingestion filter."""
    clean_keyword = filter_req.keyword.strip()
    if not clean_keyword:
        raise HTTPException(status_code=400, detail="Filter keyword cannot be empty")

    clean_field = filter_req.field.lower()
    if clean_field not in ["subject", "sender", "body", "any"]:
        clean_field = "any"

    # Check for duplicate
    existing = db.query(KeywordFilter).filter(
        KeywordFilter.keyword == clean_keyword,
        KeywordFilter.field == clean_field
    ).first()

    if existing:
        return existing

    new_filter = KeywordFilter(
        keyword=clean_keyword,
        field=clean_field
    )
    db.add(new_filter)
    db.commit()
    db.refresh(new_filter)

    return new_filter

@router.delete("/{filter_id}")
def delete_keyword_filter(
    filter_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Deletes a global keyword filter by ID."""
    filter_obj = db.query(KeywordFilter).filter(KeywordFilter.id == filter_id).first()
    if not filter_obj:
        raise HTTPException(status_code=404, detail="Filter not found")

    keyword_text = filter_obj.keyword
    db.delete(filter_obj)
    db.commit()

    return {"message": f"Successfully deleted filter '{keyword_text}'"}
