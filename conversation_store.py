
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from model import Conversation, Message
from uuid import uuid4


async def get_or_create_conversation(
    session: AsyncSession,
    user_id: str,
    conversation_id: str | None = None,
):
    if conversation_id is None:
        conversation = Conversation(
            id=uuid4().hex,
            user_id=user_id,
        )
        session.add(conversation)
        await session.flush()
        conversation_id = conversation.id

    else:
        result = await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conversation = result.scalar_one_or_none()

        if conversation is None:
            raise ValueError("Conversation not found.")

    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(
            Message.created_at.desc(),
            Message.id.desc(),
        )
        .limit(10)
    )

    saved_messages = result.scalars().all()

    history = [
        {"role": message.role, "content": message.content}
        for message in reversed(saved_messages)
    ]

    return conversation_id, history



async def save_conversation(
    session: AsyncSession,
    conversation_id: str,
    history: list,
    first_message: str,
):
    # Find the conversation
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id
        )
    )
    conversation = result.scalar_one_or_none()

    if conversation is None:
        raise ValueError("Conversation not found.")

    # Set the title from the first user message
    if conversation.title == "New Conversation":
        conversation.title = first_message[:200]

    # Save the latest user message and AI reply
    latest_messages = history[-2:]

    for message in latest_messages:
        session.add(
            Message(
                conversation_id=conversation_id,
                role=message["role"],
                content=message["content"],
            )
        )

    await session.commit()

