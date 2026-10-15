from uuid import uuid4
from pathlib import Path
from fastapi import FastAPI, HTTPException
from groq import APIError, RateLimitError, APITimeoutError, APIConnectionError
from pydantic import BaseModel, Field, field_validator
from ai_client import client
from conversation_store import get_or_create_conversation, save_conversation
import logging
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select,func, delete
from sqlalchemy.exc import IntegrityError

from model import Conversation, Message,  User
from schemas import RegisterRequest, UserResponse , ConversationResponse, LoginRequest, PaginatedConversationsResponse
from security import hash_password, verify_password
from auth_security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token
from auth_security import get_current_user_id
from fastapi.middleware.cors import CORSMiddleware

from database import get_db

app = FastAPI(title="AI Chatbot API")

BASE_DIR = Path(__file__).resolve().parent

PROMPT_FILE = BASE_DIR / "prompts" / "system_prompt.txt"

SYSTEM_PROMPT = PROMPT_FILE.read_text(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id:str | None = Field(
    default = None,
    min_length=1,
    max_length=100
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Message cannot contain only spaces.")

        return value
    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()

            if not value:
                raise ValueError("Conversation ID cannot contain only spaces.")

        return value


# Temporary memory: one shared conversation
chat_history = []    

@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }

@app.get("/")
async def home():
    return {"message":"Welcome to the AI Chatbot API!"}


@app.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
):
    # Step 1: Load the conversation from PostgreSQL
    try:
        conversation_id, history = await get_or_create_conversation(
            session,
            user_id,
            request.conversation_id,
        )
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    # Step 2: Prepare messages for Groq
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": request.message},
    ]

    try:
        # Step 3: Request the AI response
        completion = await client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
        )

        ai_reply = completion.choices[0].message.content

        if ai_reply is None:
            raise HTTPException(
                status_code=502,
                detail="The AI service returned an empty response.",
            )

    except RateLimitError:
        logger.warning("Groq rate limit exceeded.")
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
        )

    except APITimeoutError:
        logger.warning("Groq API request timed out.")
        raise HTTPException(
            status_code=504,
            detail="The AI service took too long to respond. Please try again.",
        )

    except APIConnectionError:
        logger.warning("Unable to connect to the Groq API.")
        raise HTTPException(
            status_code=503,
            detail="Unable to connect to the AI service. Please try again later.",
        )

    except APIError:
        logger.warning("AI service could not process the request.")
        raise HTTPException(
            status_code=502,
            detail="The AI service could not process your request.",
        )

    # Step 4: Save the latest user message and AI reply
    updated_history = [
        *history,
        {"role": "user", "content": request.message},
        {"role": "assistant", "content": ai_reply},
    ]

    await save_conversation(
    session,
    conversation_id,
    updated_history,
    first_message=history[0]["content"]
    if history
    else request.message,
)

    logger.info("AI response generated successfully")

    # Step 5: Return the response
    return {
        "conversation_id": conversation_id,
        "user_message": request.message,
        "reply": ai_reply,
        "history_messages": len(updated_history),
    }


@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=201,
)
async def register(
    request: RegisterRequest,
    session: AsyncSession = Depends(get_db),
):
    # Step 1: Check whether the email already exists
    result = await session.execute(
        select(User).where(User.email == request.email)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        )

    # Step 2: Create a user with a hashed password
    user = User(
        full_name=request.full_name,
        email=request.email,
        hashed_password=hash_password(request.password),
    )

    # Step 3: Save the user in PostgreSQL
    session.add(user)

    try:
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        )

    # Step 4: Return safe user details
    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
    )



@app.post("/auth/login")
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_db),
):
    # Step 1: Find the registered user by email
    result = await session.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()

    # Step 2: Verify credentials
    if user is None or not verify_password(
        request.password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    # Step 3: Check whether the account is active
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="This account is inactive.",
        )

    # Step 4: Generate a JWT access token
    access_token = create_access_token(user.id)

    # Step 5: Return the token
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@app.get("/auth/me", response_model=UserResponse)
async def get_my_profile(
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(User).where(User.id == user_id)
    )

    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="This account is inactive.",
        )

    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
    )



@app.get(
    "/conversations",
    response_model=PaginatedConversationsResponse,
)
async def get_my_conversations(
    page: int = 1,
    page_size: int = 10,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
):
    if page < 1:
        raise HTTPException(
            status_code=400,
            detail="Page must be at least 1.",
        )

    if page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=400,
            detail="Page size must be between 1 and 100.",
        )

    count_result = await session.execute(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.user_id == user_id)
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size

    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.id.desc())
        .offset(offset)
        .limit(page_size)
    )

    conversations = result.scalars().all()
    total_pages = (total + page_size - 1) // page_size

    return {
        "items": [
            ConversationResponse(
                id=conversation.id,
                title=conversation.title,
                user_id=conversation.user_id,
            )
            for conversation in conversations
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
):
    # Step 1: Find the conversation owned by the logged-in user
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()

    # Step 2: Return 404 if it doesn't exist or isn't owned by this user
    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    # Step 3: Delete all messages belonging to this conversation
    await session.execute(
        delete(Message).where(
            Message.conversation_id == conversation_id
        )
    )

    # Step 4: Delete the conversation
    await session.delete(conversation)

    # Step 5: Commit both deletions together
    await session.commit()

    return {
        "message": "Conversation and its messages deleted successfully.",
        "conversation_id": conversation_id,
    }


@app.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
):
    # 1. Verify that this conversation belongs to the logged-in user
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    # 2. Retrieve the conversation's messages in chronological order
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(
            Message.created_at.asc(),
            Message.id.asc(),
        )
    )
    messages = result.scalars().all()

    # 3. Return the conversation title and messages
    return {
        "conversation_id": conversation.id,
        "title": conversation.title,
        "messages": [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in messages
        ],
    }
