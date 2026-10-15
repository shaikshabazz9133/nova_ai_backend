
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from conversation_store import get_or_create_conversation
from main import app

from groq import APITimeoutError
from groq import RateLimitError
import httpx
from groq import APIConnectionError
from groq import APIError

client = TestClient(app)


def test_chat_endpoint():
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Python is a programming language."
                )
            )
        ]
    )

    with patch(
        "main.client.chat.completions.create",
        new_callable=AsyncMock,
    ) as mock_groq:
        mock_groq.return_value = fake_response

        response = client.post(
            "/chat",
            json={"message": "What is Python?"},
        )

    assert response.status_code == 200
    assert response.json()["reply"] == (
        "Python is a programming language."
    )
    mock_groq.assert_awaited_once()


def test_chat_rejects_empty_message():
    response = client.post(
        "/chat",
        json={"message": ""},
    )

    assert response.status_code == 422


def test_chat_rejects_missing_message():
    response = client.post(
        "/chat",
        json={},
    )

    assert response.status_code == 422


def test_chat_rejects_message_over_4000_characters():
    response = client.post(
        "/chat",
        json={"message": "a" * 4001},
    )

    assert response.status_code == 422


def test_chat_rejects_whitespace_only_message():
    response = client.post(
        "/chat",
        json={"message": "     "},
    )

    assert response.status_code == 422


def test_chat_rejects_empty_conversation_id():
    response = client.post(
        "/chat",
        json={
            "message": "Hello",
            "conversation_id": "",
        },
    )

    assert response.status_code == 422


def test_chat_rejects_long_conversation_id():
    response = client.post(
        "/chat",
        json={
            "message": "Hello",
            "conversation_id": "a" * 101,
        },
    )

    assert response.status_code == 422



def test_chat_handles_groq_timeout():
    with patch(
        "main.client.chat.completions.create",
        new_callable=AsyncMock,
    ) as mock_groq:
        mock_groq.side_effect = APITimeoutError(
            request=None
        )

        response = client.post(
            "/chat",
            json={"message": "What is Python?"},
        )

    assert response.status_code == 504


def test_chat_handles_groq_rate_limit():
    fake_response = httpx.Response(
        status_code=429,
        request=httpx.Request(
            "POST",
            "https://api.groq.com/openai/v1/chat/completions",
        ),
    )

    with patch(
        "main.client.chat.completions.create",
        new_callable=AsyncMock,
    ) as mock_groq:
        mock_groq.side_effect = RateLimitError(
            "Rate limit exceeded",
            response=fake_response,
            body=None,
        )

        response = client.post(
            "/chat",
            json={"message": "What is Python?"},
        )

    assert response.status_code == 429


def test_chat_handles_groq_connection_error():
    fake_request = httpx.Request(
        "POST",
        "https://api.groq.com/openai/v1/chat/completions",
    )

    with patch(
        "main.client.chat.completions.create",
        new_callable=AsyncMock,
    ) as mock_groq:
        mock_groq.side_effect = APIConnectionError(
            request=fake_request
        )

        response = client.post(
            "/chat",
            json={"message": "What is Python?"},
        )

    assert response.status_code == 503


def test_chat_handles_general_groq_api_error():
    fake_response = httpx.Response(
        status_code=500,
        request=httpx.Request(
            "POST",
            "https://api.groq.com/openai/v1/chat/completions",
        ),
    )

    with patch(
        "main.client.chat.completions.create",
        new_callable=AsyncMock,
    ) as mock_groq:
        mock_groq.side_effect = APIError(
            "Groq API error",
            request=fake_response.request,
            body=None,
        )

        response = client.post(
            "/chat",
            json={"message": "What is Python?"},
        )

    assert response.status_code == 502


def test_chat_does_not_save_history_after_timeout():
    conversation_id = "timeout-history-test"

    fake_request = httpx.Request(
        "POST",
        "https://api.groq.com/openai/v1/chat/completions",
    )

    with patch(
        "main.client.chat.completions.create",
        new_callable=AsyncMock,
    ) as mock_groq:
        mock_groq.side_effect = APITimeoutError(
            request=fake_request
        )

        response = client.post(
            "/chat",
            json={
                "message": "What is Python?",
                "conversation_id": conversation_id,
            },
        )

    assert response.status_code == 504

    _, saved_history = get_or_create_conversation(conversation_id)
    assert saved_history == []
