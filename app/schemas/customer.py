from pydantic import BaseModel,EmailStr,Field


class CustomerCreate(BaseModel):
      name: str = Field(min_length=2,max_length=100)
      email: EmailStr



class CustomerResponse(BaseModel):
    id:int
    name: str
    email: EmailStr
    active:bool