from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from conftest import ROOT, TEST_KEY, error_response, fixture, make_response

from ayinbox_api import operations as ops
from ayinbox_api.params import InputError
from ayinbox_api.runner import AyInboxToolError

CAMPAIGN_ID = "11111111-1111-4111-8111-111111111111"
CONTACT_ID = "22222222-2222-4222-8222-111111111111"
MAILBOX_ID = "33333333-3333-4333-8333-111111111111"


def load_tool(name: str):
    spec = importlib.util.spec_from_file_location(f"tool_{name}", ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from dify_plugin import Tool

    classes = [v for v in vars(module).values() if isinstance(v, type) and v is not Tool and issubclass(v, Tool)]
    assert len(classes) == 1, f"tools/{name}.py must define exactly one Tool subclass"
    return classes[0].from_credentials({"api_key": TEST_KEY})


def invoke(name: str, params: dict) -> list:
    return list(load_tool(name)._invoke(params))


def test_get_identity(client, http):
    http.json("GET", "/v1/me", fixture("me.json"))
    result = ops.get_identity(client, {})
    assert result.data["organization_name"] == "Example Co"
    assert "read_campaigns, read_contacts, write_contacts" in result.summary


def test_list_campaigns_builds_query(client, http):
    http.json("GET", "/v1/campaigns", fixture("campaigns_list.json"))
    result = ops.list_campaigns(client, {"query": " Q4 ", "status": "draft", "cursor": "c1_abc", "limit": 10.0})
    assert http.last()["params"] == {"q": "Q4", "status": "draft", "cursor": "c1_abc", "limit": "10"}
    assert "2 campaigns of 3." in result.summary
    assert "cursor=c1_ZmFrZS1jdXJzb3ItcGFnZS0y" in result.summary
    assert result.data["data"][0]["name"] == "Q4 outreach"


def test_list_campaigns_any_status_and_default_limit(client, http):
    http.json("GET", "/v1/campaigns", fixture("campaigns_list.json"))
    ops.list_campaigns(client, {"status": "any"})
    assert http.last()["params"] == {"limit": "25"}


@pytest.mark.parametrize("bad", [{"status": "running"}, {"limit": 0}, {"limit": 101}, {"limit": 2.5}])
def test_list_campaigns_refuses_bad_input(client, bad):
    with pytest.raises(InputError):
        ops.list_campaigns(client, bad)


def test_get_campaign_with_stats(client, http):
    http.json("GET", f"/v1/campaigns/{CAMPAIGN_ID}", fixture("campaign.json"))
    http.json("GET", f"/v1/analytics/campaigns/{CAMPAIGN_ID}", fixture("analytics_campaign.json"))
    result = ops.get_campaign(client, {"campaign_id": CAMPAIGN_ID.upper()})
    assert result.data["stats"]["summary"]["replies"] == 9
    assert "sent 180" in result.summary and "replies 9 (4 positive)" in result.summary


def test_get_campaign_without_analytics_scope(client, http):
    http.json("GET", f"/v1/campaigns/{CAMPAIGN_ID}", fixture("campaign.json"))
    http.add("GET", f"/v1/analytics/campaigns/{CAMPAIGN_ID}", error_response("403_forbidden.json"))
    result = ops.get_campaign(client, {"campaign_id": CAMPAIGN_ID})
    assert result.data["stats"] is None
    assert "READ_ANALYTICS" in result.data["stats_unavailable"]


def test_get_campaign_skips_stats(client, http):
    http.json("GET", f"/v1/campaigns/{CAMPAIGN_ID}", fixture("campaign.json"))
    ops.get_campaign(client, {"campaign_id": CAMPAIGN_ID, "include_stats": False})
    assert len(http.calls) == 1


def test_get_campaign_refuses_non_uuid(client):
    with pytest.raises(InputError):
        ops.get_campaign(client, {"campaign_id": "../me"})


def test_create_campaign_draft_body(client, http):
    http.json("POST", "/v1/campaigns", fixture("campaign.json"))
    result = ops.create_campaign_draft(
        client,
        {
            "name": "Q4 outreach",
            "first_subject": "Quick question",
            "first_body": "Hi {{first_name}},",
            "steps_json": '[{"body_plain": "Following up.", "wait_after": 3}]',
            "daily_limit": 30,
            "timezone": "Europe/London",
            "stop_on_reply": True,
            "sender_mailbox_ids": f"{MAILBOX_ID}",
            "idempotency_key": "create-1",
        },
    )
    call = http.last()
    assert call["json"] == {
        "name": "Q4 outreach",
        "daily_limit": 30,
        "timezone": "Europe/London",
        "stop_on_reply": True,
        "sender_strategy": "explicit",
        "senders": [{"email_account_id": MAILBOX_ID}],
        "steps": [
            {"subject": "Quick question", "body_plain": "Hi {{first_name}},"},
            {"body_plain": "Following up.", "wait_after": 3},
        ],
    }
    assert call["headers"]["Idempotency-Key"] == "create-1"
    assert "status" not in call["json"]
    assert "sends nothing" in result.summary


@pytest.mark.parametrize(
    "bad",
    [
        {"name": ""},
        {"name": "x", "steps_json": "{not json"},
        {"name": "x", "steps_json": '{"a": 1}'},
        {"name": "x", "steps_json": '[{"status": "active"}]'},
        {"name": "x", "daily_limit": 2},
        {"name": "x", "sender_mailbox_ids": "not-a-uuid"},
    ],
)
def test_create_campaign_draft_refuses_bad_input(client, bad):
    with pytest.raises(InputError):
        ops.create_campaign_draft(client, bad)


def test_pause_campaign(client, http):
    http.json("POST", f"/v1/campaigns/{CAMPAIGN_ID}/stop", fixture("campaign_stop.json"))
    result = ops.pause_campaign(client, {"campaign_id": CAMPAIGN_ID})
    assert http.last()["json"] is None
    assert result.data == {"campaign_id": CAMPAIGN_ID, "status": "stopped"}


def test_search_contacts_body_and_query(client, http):
    http.json("POST", "/v1/contacts/search", fixture("contacts_list.json"))
    result = ops.search_contacts(
        client,
        {
            "query": "lee",
            "campaign_id": CAMPAIGN_ID,
            "subscribed": "true",
            "verification_status": "valid",
            "sort_by": "email",
            "ascending": True,
            "limit": 5,
        },
    )
    call = http.last()
    assert call["params"] == {"limit": "5"}
    assert call["json"] == {
        "query": "lee",
        "campaign_ids": [CAMPAIGN_ID],
        "subscribed": True,
        "verification_status": "valid",
        "sort_by": "email",
        "reverse": True,
    }
    assert "Lee Example <lee@example.com>, Example Co" in result.summary
    assert "No more results." in result.summary


def test_search_contacts_empty_filters_send_empty_object(client, http):
    http.json("POST", "/v1/contacts/search", fixture("contacts_list.json"))
    ops.search_contacts(client, {"subscribed": "any", "sort_by": "any"})
    assert http.last()["json"] == {}


def test_create_contact(client, http):
    http.json("POST", "/v1/contacts", fixture("contacts_create.json"))
    result = ops.create_contact(
        client,
        {"email": "lee@example.com", "first_name": "Lee", "custom_fields": '{"title": "Head of Ops", "seats": 12}'},
    )
    body = http.last()["json"]
    assert body == {
        "email": "lee@example.com",
        "first_name": "Lee",
        "custom_fields": {"title": "Head of Ops", "seats": "12"},
    }
    assert "campaigns" not in body
    assert result.data["id"] == CONTACT_ID
    assert "not added to any campaign" in result.summary


@pytest.mark.parametrize("bad", [{}, {"email": "nobody"}, {"email": "a@b.c", "custom_fields": "[1]"}])
def test_create_contact_refuses_bad_input(client, bad):
    with pytest.raises(InputError):
        ops.create_contact(client, bad)


def test_update_contact_merges_custom_fields_and_only_unsubscribes(client, http):
    http.json("GET", f"/v1/contacts/{CONTACT_ID}", fixture("contact.json"))
    http.json("PATCH", f"/v1/contacts/{CONTACT_ID}", fixture("contacts_create.json")[0])
    result = ops.update_contact(
        client,
        {"contact_id": CONTACT_ID, "company": "New Co", "custom_fields": '{"team": "Ops"}', "unsubscribe": True},
    )
    body = http.last()["json"]
    assert body == {
        "company": "New Co",
        "subscribed": False,
        "custom_fields": {"title": "Head of Ops", "team": "Ops"},
    }
    assert "company" in result.summary


def test_update_contact_never_resubscribes(client, http):
    http.json("PATCH", f"/v1/contacts/{CONTACT_ID}", fixture("contacts_create.json")[0])
    ops.update_contact(client, {"contact_id": CONTACT_ID, "first_name": "Lee", "unsubscribe": False})
    assert http.last()["json"] == {"first_name": "Lee"}


def test_update_contact_needs_a_field(client):
    with pytest.raises(InputError):
        ops.update_contact(client, {"contact_id": CONTACT_ID})


def test_list_mailboxes(client, http):
    http.json("GET", "/v1/emails", fixture("mailboxes_list.json"))
    result = ops.list_mailboxes(client, {"query": "sales"})
    assert http.last()["params"] == {"q": "sales", "limit": "25"}
    assert "sales@example.com (gmail, active, warmup on)" in result.summary


def test_list_threads_query(client, http):
    http.json("GET", "/v1/unibox", fixture("unibox_threads.json"))
    result = ops.list_threads(
        client,
        {
            "folder": "inbox",
            "direction": "received",
            "unread_only": True,
            "awaiting_reply": False,
            "from_address": "lee@example.com",
            "mailbox_id": MAILBOX_ID,
            "limit": 10,
        },
    )
    assert http.last()["params"] == {
        "folder": "inbox",
        "direction": "received",
        "unseen": "true",
        "from": "lee@example.com",
        "email_id": MAILBOX_ID,
        "limit": "10",
    }
    assert result.data["untrusted_content"] is True
    assert "thread_id thread-example-001" in result.summary
    assert "cursor=c1_ZmFrZS11bmlib3gtY3Vyc29y" in result.summary


def test_get_thread_previews(client, http):
    http.json("GET", "/v1/unibox/thread", fixture("unibox_thread.json"))
    result = ops.get_thread(client, {"thread_id": "thread-example-001"})
    assert http.last()["params"] == {"thread_id": "thread-example-001", "limit": "50"}
    assert len(http.calls) == 1
    assert "Thanks, Tuesday works for me." in result.summary


def test_get_thread_with_bodies(client, http):
    http.json("GET", "/v1/unibox/thread", fixture("unibox_thread.json"))
    http.json("GET", "/v1/unibox/55555555-5555-4555-8555-222222222222", fixture("unibox_message.json"))
    http.json("GET", "/v1/unibox/55555555-5555-4555-8555-111111111111", fixture("unibox_message.json"))
    result = ops.get_thread(
        client, {"thread_id": "thread-example-001", "mailbox_id": MAILBOX_ID, "include_bodies": True}
    )
    assert len(http.calls) == 3
    assert result.data["messages"][0]["body_plain"] == "Thanks, Tuesday works for me.\n"
    assert result.data["untrusted_content"] is True


def test_save_email_draft_puts_and_never_sends(client, http, monkeypatch):
    draft_id = "bbbbbbbb-bbbb-4bbb-8bbb-111111111111"
    monkeypatch.setattr(ops.p, "new_uuid", lambda: draft_id)
    http.json("PUT", f"/v1/unibox/drafts/{draft_id}", {"id": draft_id})
    result = ops.save_email_draft(
        client,
        {
            "mailbox_id": MAILBOX_ID,
            "to": "lee@example.com, sam@example.org",
            "subject": "Re: Quick question",
            "body": "Tuesday at 10 works.",
        },
    )
    call = http.last()
    assert call["method"] == "PUT"
    assert call["json"] == {
        "email_account_id": MAILBOX_ID,
        "to": ["lee@example.com", "sam@example.org"],
        "cc": [],
        "bcc": [],
        "subject": "Re: Quick question",
        "body": "Tuesday at 10 works.",
    }
    assert result.data["sent"] is False
    assert "Nothing was sent" in result.summary


def test_save_email_draft_uses_given_id(client, http):
    draft_id = str(uuid.uuid4())
    http.json("PUT", f"/v1/unibox/drafts/{draft_id}", {"id": draft_id})
    ops.save_email_draft(
        client, {"mailbox_id": MAILBOX_ID, "to": "a@b.co", "subject": "s", "body": "b", "draft_id": draft_id}
    )
    assert http.last()["path"] == f"/v1/unibox/drafts/{draft_id}"


def test_save_email_draft_refuses_bad_address(client):
    with pytest.raises(InputError):
        ops.save_email_draft(client, {"mailbox_id": MAILBOX_ID, "to": "not an address", "subject": "s", "body": "b"})


def test_list_suppressions(client, http):
    http.json("GET", "/v1/suppressions", fixture("suppressions_list.json"))
    result = ops.list_suppressions(client, {"query": "example.org"})
    assert http.last()["params"] == {"q": "example.org", "limit": "25"}
    assert "no-reply@example.org (email, manual): Asked not to be contacted" in result.summary


def test_add_suppressions(client, http):
    http.json("POST", "/v1/suppressions", fixture("suppressions_add.json"))
    result = ops.add_suppressions(
        client, {"values": "new@example.org\nalready@example.org, example.net", "reason": "Asked to stop"}
    )
    assert http.last()["json"] == {
        "entries": [{"value": "new@example.org"}, {"value": "already@example.org"}, {"value": "example.net"}],
        "reason": "Asked to stop",
    }
    assert "Suppressed 1" in result.summary and "already@example.org" in result.summary


def test_operations_cover_every_tool():
    names = sorted(p.stem for p in (ROOT / "tools").glob("*.py"))
    assert names == sorted(ops.OPERATIONS)
    assert len(names) == 14


def test_no_operation_sends_or_starts():
    for name in ops.OPERATIONS:
        assert "send" not in name and "start" not in name and "reply" not in name


# Through the real Dify Tool classes


def test_tool_yields_json_then_text(patched_factory):
    patched_factory.json("GET", "/v1/me", fixture("me.json"))
    messages = invoke("get_identity", {})
    assert [m.type.value for m in messages] == ["json", "text"]
    assert messages[0].message.json_object["email"] == "dana@example.com"
    assert messages[1].message.text.startswith("Signed in as Dana Example")


@pytest.mark.parametrize("name", sorted(p.stem for p in (Path(__file__).resolve().parents[1] / "tools").glob("*.py")))
def test_every_tool_class_loads(name):
    assert load_tool(name) is not None


def test_tool_maps_403_with_scope_hint(patched_factory):
    patched_factory.add("GET", "/v1/campaigns", error_response("403_forbidden.json"))
    with pytest.raises(AyInboxToolError) as info:
        invoke("list_campaigns", {})
    text = str(info.value)
    assert "403 (forbidden)" in text
    assert "READ_CAMPAIGNS" in text
    assert "req-fixture-0001" in text
    assert TEST_KEY not in text


def test_tool_maps_401(patched_factory):
    patched_factory.add("GET", "/v1/emails", error_response("401_api_key_holder_left.json"))
    with pytest.raises(AyInboxToolError) as info:
        invoke("list_mailboxes", {})
    assert "api_key_holder_left" in str(info.value) and "plugin settings" in str(info.value)


def test_tool_maps_409_contact_email_taken(patched_factory):
    body = {
        "error": "Conflict",
        "message": "Another contact has this email.",
        "code": "contact_email_taken",
        "request_id": "req-2",
    }
    patched_factory.add("PATCH", f"/v1/contacts/{CONTACT_ID}", make_response(409, body))
    with pytest.raises(AyInboxToolError) as info:
        invoke("update_contact", {"contact_id": CONTACT_ID, "email": "taken@example.com"})
    assert "409 (contact_email_taken)" in str(info.value) and "req-2" in str(info.value)


def test_tool_maps_input_error(patched_factory):
    with pytest.raises(AyInboxToolError) as info:
        invoke("get_thread", {})
    assert str(info.value).startswith("Invalid input:")
    assert patched_factory.calls == []


def test_tool_maps_rate_limit(patched_factory, sleeps):
    patched_factory.add("GET", "/v1/suppressions", error_response("429_category_rate_limited.json"))
    with pytest.raises(AyInboxToolError) as info:
        invoke("list_suppressions", {})
    assert "429 (rate_limit_exceeded)" in str(info.value) and "Retry after 12 seconds" in str(info.value)
    assert len(patched_factory.calls) == 3


# Credential validation


def load_provider():
    spec = importlib.util.spec_from_file_location("provider_ayinbox", ROOT / "provider" / "ayinbox.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AyInboxProvider()


def test_provider_validates_against_me(patched_factory):
    patched_factory.json("GET", "/v1/me", fixture("me.json"))
    load_provider()._validate_credentials({"api_key": TEST_KEY})
    assert patched_factory.last()["path"] == "/v1/me"


def test_provider_refuses_wrong_prefix(patched_factory):
    from dify_plugin.errors.tool import ToolProviderCredentialValidationError

    with pytest.raises(ToolProviderCredentialValidationError):
        load_provider()._validate_credentials({"api_key": "sk-something"})
    assert patched_factory.calls == []


def test_provider_refuses_rejected_key(patched_factory):
    from dify_plugin.errors.tool import ToolProviderCredentialValidationError

    patched_factory.add("GET", "/v1/me", error_response("401_unauthorized.json"))
    with pytest.raises(ToolProviderCredentialValidationError) as info:
        load_provider()._validate_credentials({"api_key": TEST_KEY})
    assert "unauthorized" in str(info.value) and TEST_KEY not in str(info.value)
