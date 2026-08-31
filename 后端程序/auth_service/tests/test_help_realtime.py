import json

from app.help_realtime import HelpRealtimeHub


class _FakeRedis:
    def __init__(self):
        self.published = []
        self.values = {}

    def publish(self, channel, payload):
        self.published.append((channel, payload))

    def setex(self, key, seconds, value):
        self.values[key] = value

    def getdel(self, key):
        return self.values.pop(key, None)


def test_redis_event_contains_only_routing_metadata_and_recipient_ids():
    hub = HelpRealtimeHub()
    redis = _FakeRedis()
    delivered = []
    hub._redis = redis
    hub._deliver = delivered.append

    hub.publish(line_id=7, student_id=11, admin_ids={5, 3}, event="student_message")

    assert delivered[0]["chat_line_id"] == 7
    channel, raw = redis.published[0]
    event = json.loads(raw)
    assert channel == "help:line:7"
    assert event["student_id"] == 11
    assert event["admin_ids"] == [3, 5]
    assert "body" not in event


def test_ticket_is_bound_to_its_principal_and_can_only_be_used_once():
    hub = HelpRealtimeHub()
    hub._redis = _FakeRedis()

    ticket = hub.issue_ticket("student", 11)

    assert hub.consume_ticket(ticket, "student", 11) is True
    assert hub.consume_ticket(ticket, "student", 11) is False


def test_message_event_keeps_the_rest_serialization_as_its_payload():
    hub = HelpRealtimeHub()
    redis = _FakeRedis()
    delivered = []
    hub._redis = redis
    hub._deliver = delivered.append
    serialized = {"id": 9, "messages": [{"id": 12, "body": "已收到"}]}

    hub.publish(
        line_id=7,
        student_id=11,
        admin_ids={5},
        event="admin_message",
        serialized_payload=serialized,
    )

    assert delivered[0]["payload"] == serialized


def test_typing_event_has_no_message_content():
    hub = HelpRealtimeHub()
    redis = _FakeRedis()
    delivered = []
    hub._redis = redis
    hub._deliver = delivered.append

    hub.publish(line_id=7, student_id=11, admin_ids={5}, event="admin_typing")

    assert delivered[0]["event"] == "admin_typing"
    assert set(delivered[0]) == {"origin", "type", "event", "chat_line_id", "student_id", "admin_ids"}
