import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=200)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Currency = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{3}$")]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
AppName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
SettlementMode = Literal["simplified", "full"]


def _round_money(value: float) -> float:
    return round(value, 2)


class UserCreate(BaseModel):
    name: Name
    password: Password


class UserRead(BaseModel):
    id: int
    name: str
    is_admin: bool
    is_active: bool
    must_change_password: bool

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    name: Name | None = None
    is_admin: bool | None = None
    is_active: bool | None = None
    password: Password | None = None
    # Required when users change their own password.
    current_password: str | None = None


class ExpenseShareCreate(BaseModel):
    user_id: int
    share: float

    @field_validator("share")
    @classmethod
    def _nonzero(cls, value: float) -> float:
        value = _round_money(value)
        if value == 0:
            raise ValueError("share must not be zero")
        return value


class ExpenseCreate(BaseModel):
    date: datetime.date
    description: ShortText
    category: ShortText
    cost: float = Field(gt=0)
    currency: Currency | None = None
    comment: Comment | None = None
    shares: list[ExpenseShareCreate] = Field(min_length=1)

    @field_validator("cost")
    @classmethod
    def _round_cost(cls, value: float) -> float:
        return _round_money(value)


class ExpenseUpdate(BaseModel):
    date: datetime.date | None = None
    description: ShortText | None = None
    category: ShortText | None = None
    cost: float | None = Field(default=None, gt=0)
    currency: Currency | None = None
    comment: Comment | None = None
    shares: list[ExpenseShareCreate] | None = Field(default=None, min_length=1)

    @field_validator("cost")
    @classmethod
    def _round_cost(cls, value: float | None) -> float | None:
        return None if value is None else _round_money(value)


class ExpenseShareRead(BaseModel):
    user_id: int
    share: float

    model_config = ConfigDict(from_attributes=True)


class ExpenseRead(BaseModel):
    id: int
    date: datetime.date
    description: str
    category: str
    cost: float
    currency: str
    comment: str | None
    shares: list[ExpenseShareRead]

    model_config = ConfigDict(from_attributes=True)


class BalanceRead(BaseModel):
    user_id: int
    name: str
    balance: float


class LoginRequest(BaseModel):
    name: str
    password: str


class SettlementRead(BaseModel):
    from_user_id: int
    from_name: str
    to_user_id: int
    to_name: str
    amount: float


class SettingsRead(BaseModel):
    app_name: str
    settlement_mode: SettlementMode
    currency: str


class SettingsUpdate(BaseModel):
    app_name: AppName | None = None
    settlement_mode: SettlementMode | None = None
    currency: Currency | None = None
