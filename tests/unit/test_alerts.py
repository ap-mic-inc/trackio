import json

import pytest

from trackio import alerts
from trackio.alerts import AlertLevel, send_webhook


@pytest.fixture
def captured(monkeypatch):
    requests = []

    def fake_urlopen(req, timeout=None, context=None):
        requests.append(req)

    monkeypatch.setattr(alerts.urllib.request, "urlopen", fake_urlopen)
    return requests


@pytest.mark.parametrize(
    "url",
    [
        "https://discord.com/api/webhooks/1/token",
        "https://hooks.slack.com/services/T/B/X",
        "https://example.com/hook",
    ],
)
def test_send_webhook_sets_user_agent(captured, url):
    send_webhook(url, AlertLevel.WARN, "title", None, "proj", "run", 3)
    [req] = captured
    user_agent = req.get_header("User-agent")
    assert user_agent and not user_agent.startswith("Python-urllib")


def test_send_webhook_discord_payload(captured):
    send_webhook(
        "https://discord.com/api/webhooks/1/token",
        AlertLevel.ERROR,
        "Training diverged",
        "loss is NaN",
        "proj",
        "run-1",
        42,
    )
    [embed] = json.loads(captured[0].data)["embeds"]
    assert "Training diverged" in embed["title"]
    assert embed["description"] == "loss is NaN"
    assert "Run: run-1" in embed["footer"]["text"]
    assert "Step 42" in embed["footer"]["text"]


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://discord.com/api/webhooks/123/secret-token",
            "https://discord.com/***",
        ),
        ("https://hooks.slack.com/services/T/B/secret", "https://hooks.slack.com/***"),
        (
            "http://user:pass@internal:8080/hook?token=secret",
            "http://internal:8080/***",
        ),
        ("not a url", "<webhook>"),
    ],
)
def test_redact_webhook_url(url, expected):
    assert alerts.redact_webhook_url(url) == expected


def test_send_webhook_failure_does_not_log_secret(monkeypatch, caplog):
    def failing_urlopen(req, timeout=None, context=None):
        raise OSError("boom")

    monkeypatch.setattr(alerts.urllib.request, "urlopen", failing_urlopen)
    with caplog.at_level("WARNING", logger="trackio.alerts"):
        send_webhook(
            "https://discord.com/api/webhooks/123/secret-token",
            AlertLevel.WARN,
            "title",
            None,
            "proj",
            "run",
            None,
        )
    assert "secret-token" not in caplog.text
    assert "discord.com" in caplog.text
