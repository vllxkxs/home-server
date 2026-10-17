from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.app_settings import get_setting
from app.auth import get_current_user, get_db

router = APIRouter()

_EPSILON = 0.005


def _participants(db: Session, expenses) -> list[models.User]:
    """Active flatmates plus anyone who appears in an expense.

    Admins are not participants; one only shows up here if legacy data gives them shares.
    """
    in_expenses = {s.user_id for e in expenses for s in e.shares}
    users = db.query(models.User).order_by(models.User.name).all()
    return [u for u in users if u.id in in_expenses or (u.is_active and not u.is_admin)]


def _build_pairwise(db: Session):
    expenses = db.query(models.Expense).options(selectinload(models.Expense.shares)).all()
    users = _participants(db, expenses)
    balances = {u.id: {u1.id: 0.0 for u1 in users if u1.id != u.id} for u in users}

    for expense in expenses:
        payers = [s for s in expense.shares if s.share < 0]
        debtors = [s for s in expense.shares if s.share > 0]
        total_paid = sum(-s.share for s in payers)
        if total_paid <= 0:
            continue
        for debtor in debtors:
            for payer in payers:
                if debtor.user_id == payer.user_id:
                    continue
                portion = debtor.share * (-payer.share / total_paid)
                # balances[A][B] < 0 means A owes B
                balances[debtor.user_id][payer.user_id] -= portion
                balances[payer.user_id][debtor.user_id] += portion

    return users, balances


def _full_settlements(users, balances):
    user_map = {u.id: u.name for u in users}
    result = []

    for a_id in user_map:
        for b_id in user_map:
            if a_id >= b_id:
                continue
            val = balances[a_id].get(b_id, 0.0)
            if val < -_EPSILON:
                result.append(schemas.SettlementRead(
                    from_user_id=a_id, from_name=user_map[a_id],
                    to_user_id=b_id, to_name=user_map[b_id],
                    amount=round(-val, 2),
                ))
            elif val > _EPSILON:
                result.append(schemas.SettlementRead(
                    from_user_id=b_id, from_name=user_map[b_id],
                    to_user_id=a_id, to_name=user_map[a_id],
                    amount=round(val, 2),
                ))

    return sorted(result, key=lambda s: (s.from_name, s.to_name))


def _simplified_settlements(users, balances):
    user_map = {u.id: u.name for u in users}
    net = {u.id: sum(balances[u.id].values()) for u in users}

    debtors = sorted(
        [[-v, uid] for uid, v in net.items() if v < -_EPSILON],
        key=lambda x: -x[0],
    )
    creditors = sorted(
        [[v, uid] for uid, v in net.items() if v > _EPSILON],
        key=lambda x: -x[0],
    )

    result = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debt, d_id = debtors[i]
        credit, c_id = creditors[j]
        payment = round(min(debt, credit), 2)
        if payment > 0:
            result.append(schemas.SettlementRead(
                from_user_id=d_id, from_name=user_map[d_id],
                to_user_id=c_id, to_name=user_map[c_id],
                amount=payment,
            ))
        debtors[i][0] -= payment
        creditors[j][0] -= payment
        if debtors[i][0] < _EPSILON:
            i += 1
        if creditors[j][0] < _EPSILON:
            j += 1

    return result


@router.get("/", response_model=list[schemas.BalanceRead])
def get_balances(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    users, balances = _build_pairwise(db)
    result = []
    for u in users:
        balance = round(sum(balances[u.id].values()), 2)
        # Hide settled admins/deactivated users; they only matter while money is open.
        if (u.is_admin or not u.is_active) and abs(balance) < _EPSILON:
            continue
        result.append(schemas.BalanceRead(user_id=u.id, name=u.name, balance=balance))
    return result


@router.get("/settlements/", response_model=list[schemas.SettlementRead])
def get_settlements(
    mode: schemas.SettlementMode | None = Query(default=None, description="Defaults to the app setting"),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    users, balances = _build_pairwise(db)
    if (mode or get_setting(db, "settlement_mode")) == "full":
        return _full_settlements(users, balances)
    return _simplified_settlements(users, balances)
