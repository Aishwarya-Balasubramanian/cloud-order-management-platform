from decimal import Decimal

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    sku: str =Field(min_length=3,max_length=50)
    name: str =Field(min_length=2,max_length=150)
    price: Decimal = Field(gt=0)



class ProductResponse(BaseModel):
    id: int
    sku: str
    name: str
    price: Decimal
    active: bool