"""Validated purchase-order proposal and persistence models."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PurchaseOrderItem(BaseModel):
    """A purchase-order line item grounded in an approved catalog entry."""

    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=128)
    item_name: str = Field(min_length=1, max_length=300)
    vendor_id: str = Field(min_length=1, max_length=128)
    vendor_name: str = Field(min_length=1, max_length=300)
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0, allow_inf_nan=False)
    currency: Literal["USD"] = "USD"
    description: str | None = Field(default=None, max_length=2000)
    line_total: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class PurchaseOrderProposal(BaseModel):
    """The model-generated portion of a purchase-order draft."""

    model_config = ConfigDict(extra="forbid")

    items: list[PurchaseOrderItem] = Field(min_length=1)
    department: str | None = Field(default=None, max_length=200)
    cost_center_id: str | None = Field(default=None, max_length=128)


class PurchaseOrder(BaseModel):
    """A complete purchase order or purchase-order draft stored in workflow state."""

    po_id: str | None = Field(default=None, max_length=128)
    thread_id: str | None = Field(default=None, max_length=128)
    requester_name: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    cost_center_id: str | None = Field(default=None, max_length=128)
    items: list[PurchaseOrderItem] = Field(min_length=1)
    total_amount: float = Field(gt=0, allow_inf_nan=False)
    currency: Literal["USD"] = "USD"
    status: str = Field(default="DRAFT", min_length=1, max_length=40)
    approver_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_totals(self) -> "PurchaseOrder":
        calculated_total = round(
            sum(item.quantity * item.unit_price for item in self.items), 2
        )
        if not math.isclose(
            calculated_total, self.total_amount, rel_tol=0, abs_tol=0.01
        ):
            raise ValueError("total_amount must equal the sum of the line items")

        for item in self.items:
            calculated_line_total = round(item.quantity * item.unit_price, 2)
            if item.line_total is None:
                item.line_total = calculated_line_total
            elif not math.isclose(
                calculated_line_total, item.line_total, rel_tol=0, abs_tol=0.01
            ):
                raise ValueError("line_total must equal quantity multiplied by unit_price")
        return self