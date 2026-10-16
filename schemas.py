
from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Full name cannot be empty.")

        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserResponse(BaseModel):
    id: str
    full_name: str
    email: EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()  

class ConversationResponse(BaseModel):
    id: str
    title: str
    user_id: str

class PaginatedConversationsResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int    

class EditMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

