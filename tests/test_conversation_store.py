
from conversation_store import (
    get_or_create_conversation,
    save_conversation,
)


def test_conversation_history_is_saved():
    conversation_id, _ = get_or_create_conversation()

    history = [
        {"role": "user", "content": "My name is Alex."},
        {"role": "assistant", "content": "Nice to meet you, Alex!"},
    ]

    save_conversation(conversation_id, history)

    saved_id, saved_history = get_or_create_conversation(
        conversation_id
    )

    assert saved_id == conversation_id
    assert saved_history == history


def test_conversations_are_isolated():
    conversation_a = "conversation-a"
    conversation_b = "conversation-b"

    history_a = [
        {"role": "user", "content": "My name is Alex."}
    ]

    history_b = [
        {"role": "user", "content": "My name is Sarah."}
    ]

    save_conversation(conversation_a, history_a)
    save_conversation(conversation_b, history_b)

    _, retrieved_a = get_or_create_conversation(conversation_a)
    _, retrieved_b = get_or_create_conversation(conversation_b)

    assert retrieved_a == history_a
    assert retrieved_b == history_b
    assert retrieved_a != retrieved_b


def test_conversation_history_keeps_last_10_messages():
    conversation_id = "history-limit-test"

    history = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(15)
    ]

    save_conversation(conversation_id, history)

    _, saved_history = get_or_create_conversation(conversation_id)

    assert len(saved_history) == 10
    assert saved_history[0]["content"] == "Message 5"
    assert saved_history[-1]["content"] == "Message 14"


def test_new_conversations_get_unique_ids():
    conversation_id_a, history_a = get_or_create_conversation()
    conversation_id_b, history_b = get_or_create_conversation()

    assert conversation_id_a != conversation_id_b
    assert history_a == []
    assert history_b == []
