from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.app_settings import get_setting
from app.auth import get_current_user, get_db

router = APIRouter()


def validate_shares(shares, cost: float):
    total = sum(s.share for s in shares)
    total_positive = sum(s.share for s in shares if s.share > 0)
    total_negative = sum(s.share for s in shares if s.share < 0)

    if abs(total) > 0.01:
        raise HTTPException(status_code=400, detail="Shares must net to zero")
    if abs(total_positive - cost) > 0.01 or abs(total_negative + cost) > 0.01:
        raise HTTPException(status_code=400, detail="Positive and negative shares must match total amount")


def validate_share_users(db: Session, shares, already_in_expense: set[int] = frozenset()):
    """Share users must exist. New participants must be active flatmates (not admins).

    Users already in an expense may stay in it when it is edited, even if they were
    deactivated since, so old expenses remain editable.
    """
    for user_id in {s.user_id for s in shares}:
        user = db.get(models.User, user_id)
        if not user:
            raise HTTPException(status_code=400, detail=f"User {user_id} not found")
        if user_id in already_in_expense:
            continue
        if user.is_admin:
            raise HTTPException(status_code=400, detail=f"Admin '{user.name}' cannot take part in expenses")
        if not user.is_active:
            raise HTTPException(status_code=400, detail=f"User '{user.name}' is deactivated")


def _get_expense_or_404(db: Session, expense_id: int) -> models.Expense:
    expense = db.get(models.Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


def _can_view(user: models.User, expense: models.Expense) -> bool:
    return user.is_admin or any(s.user_id == user.id for s in expense.shares)


def _can_edit(user: models.User, expense: models.Expense) -> bool:
    return user.is_admin or any(s.user_id == user.id and s.share < 0 for s in expense.shares)


@router.post("/", response_model=schemas.ExpenseRead, status_code=status.HTTP_201_CREATED,
             responses={400: {"description": "Invalid expense data"}})
def create_expense(
    expense: schemas.ExpenseCreate,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    validate_shares(expense.shares, expense.cost)
    validate_share_users(db, expense.shares)

    db_expense = models.Expense(
        date=expense.date,
        description=expense.description,
        category=expense.category,
        cost=expense.cost,
        currency=expense.currency or get_setting(db, "currency"),
        comment=expense.comment or None,
        shares=[models.ExpenseShare(user_id=s.user_id, share=s.share) for s in expense.shares],
    )
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)
    return db_expense


@router.patch("/{expense_id}", response_model=schemas.ExpenseRead, responses={400: {"description": "Invalid expense data"},
                                         404: {"description": "Expense not found"}})
def update_expense(
    expense_id: int,
    expense: schemas.ExpenseUpdate,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    db_expense = _get_expense_or_404(db, expense_id)
    if not _can_edit(_current_user, db_expense):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Validate everything before touching the row, so a rejected update changes nothing.
    new_cost = expense.cost if expense.cost is not None else db_expense.cost
    new_shares = expense.shares if expense.shares is not None else db_expense.shares
    if expense.shares is not None or expense.cost is not None:
        validate_shares(new_shares, new_cost)
    if expense.shares is not None:
        validate_share_users(db, expense.shares, already_in_expense={s.user_id for s in db_expense.shares})

    for field in ("date", "description", "category", "cost", "currency"):
        value = getattr(expense, field)
        if value is not None:
            setattr(db_expense, field, value)
    if expense.comment is not None:
        db_expense.comment = expense.comment or None
    if expense.shares is not None:
        db_expense.shares = [models.ExpenseShare(user_id=s.user_id, share=s.share) for s in expense.shares]

    db.commit()
    db.refresh(db_expense)
    return db_expense


@router.get("/", response_model=list[schemas.ExpenseRead], responses={403: {"description": "Forbidden"}})
def list_expenses(
    user_id: int | None = Query(default=None, description="Only expenses this user takes part in"),
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    if not _current_user.is_admin:
        if user_id is not None and user_id != _current_user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        user_id = _current_user.id

    query = db.query(models.Expense).options(selectinload(models.Expense.shares))
    if user_id is not None:
        query = query.filter(models.Expense.shares.any(models.ExpenseShare.user_id == user_id))
    return query.order_by(models.Expense.date.desc(), models.Expense.id.desc()).all()


@router.get("/categories", response_model=list[str])
def list_categories(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Expense.category).distinct()
    if not _current_user.is_admin:
        query = query.filter(models.Expense.shares.any(models.ExpenseShare.user_id == _current_user.id))
    return sorted(r[0] for r in query.all() if r[0])


@router.get("/{expense_id}", response_model=schemas.ExpenseRead, responses={404: {"description": "Expense not found"}})
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    expense = _get_expense_or_404(db, expense_id)
    if not _can_view(_current_user, expense):
        raise HTTPException(status_code=403, detail="Forbidden")
    return expense


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses={404: {"description": "Expense not found"}})
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    expense = _get_expense_or_404(db, expense_id)
    if not _can_edit(_current_user, expense):
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(expense)
    db.commit()
    return None
