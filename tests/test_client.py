from __future__ import annotations

import pytest
import requests
from conftest import TEST_KEY, error_response, fixture, make_response

from ayinbox_api import errors
from ayinbox_api.client import USER_AGENT, AyInboxClient


def test_sends_auth_user_agent_and_accept(client, http):
    http.json("GET", "/v1/me", fixture("me.json"))
    assert client.request("GET", "/me")["email"] == "dana@example.com"
    call = http.last()
    assert call["url"] == "https://api.ayinbox.com/v1/me"
    assert call["headers"]["Authorization"] == f"Bearer {TEST_KEY}"
    assert call["headers"]["User-Agent"] == USER_AGENT == "ayinbox-dify/0.1.0"
    assert call["headers"]["Accept"] == "application/json"
    assert "Content-Type" not in call["headers"]
    assert call["allow_redirects"] is False
    assert call["timeout"] == 30.0


def test_key_never_in_repr_or_errors(client, http):
    http.add("GET", "/v1/me", error_response("401_unauthorized.json"))
    assert TEST_KEY not in repr(client)
    with pytest.raises(errors.AuthenticationError) as info:
        client.request("GET", "/me")
    assert TEST_KEY not in info.value.describe()


def test_empty_key_refused():
    with pytest.raises(ValueError):
        AyInboxClient("  ")


def test_query_drops_empty_values_and_encodes_booleans(client, http):
    http.json("GET", "/v1/unibox", {"data": [], "pagination": {}})
    client.request("GET", "/unibox", query={"unseen": True, "folder": None, "subject": "", "limit": 5})
    assert http.last()["params"] == {"unseen": "true", "limit": "5"}


def test_body_sets_content_type(client, http):
    http.json("POST", "/v1/suppressions", fixture("suppressions_add.json"))
    client.request("POST", "/suppressions", body={"entries": []}, idempotency_key="key-1")
    call = http.last()
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["headers"]["Idempotency-Key"] == "key-1"
    assert call["json"] == {"entries": []}


def test_invalid_idempotency_key_refused(client):
    with pytest.raises(ValueError):
        client.request("POST", "/campaigns", body={}, idempotency_key="has space")


def test_empty_body_returns_none(client, http):
    http.add("POST", "/v1/campaigns/x/stop", make_response(204, None))
    assert client.request("POST", "/campaigns/x/stop") is None


ERROR_CASES = [
    ("400_bad_request.json", errors.BadRequestError, "bad_request"),
    ("400_invalid_cursor.json", errors.BadRequestError, "bad_request"),
    ("401_unauthorized.json", errors.AuthenticationError, "unauthorized"),
    ("401_api_key_holder_left.json", errors.AuthenticationError, "api_key_holder_left"),
    ("402_insufficient_credits.json", errors.PaymentRequiredError, "insufficient_credits"),
    ("403_forbidden.json", errors.PermissionDeniedError, "forbidden"),
    ("403_api_key_mailbox_limited.json", errors.PermissionDeniedError, "api_key_mailbox_limited"),
    ("404_not_found.json", errors.NotFoundError, "not_found"),
    ("409_conflict.json", errors.ConflictError, "conflict"),
    ("409_idempotency_outcome_unknown.json", errors.ConflictError, "idempotency_outcome_unknown"),
    ("409_idempotent_secret_withheld.json", errors.ConflictError, "idempotent_secret_withheld"),
    ("422_unprocessable.json", errors.UnprocessableError, "unprocessable"),
    ("429_api_key_rate_limited.json", errors.RateLimitError, "rate_limit_exceeded"),
    ("429_category_rate_limited.json", errors.RateLimitError, "rate_limit_exceeded"),
    ("500_internal_error.json", errors.InternalServerError, "internal_error"),
    ("503_service_unavailable.json", errors.ServiceUnavailableError, "service_unavailable"),
]


@pytest.mark.parametrize(("name", "cls", "code"), ERROR_CASES)
def test_error_mapping(http, name, cls, code):
    client = AyInboxClient(TEST_KEY, http=http, max_retries=0)
    http.add("GET", "/v1/campaigns", error_response(name))
    with pytest.raises(cls) as info:
        client.request("GET", "/campaigns")
    err = info.value
    assert err.code == code
    assert err.status == int(name[:3])
    assert err.message == fixture(f"errors/{name}")["message"]
    if name != "429_category_rate_limited.json":
        assert err.request_id == "req-fixture-0001"
    assert code in err.describe()


def test_category_429_without_code_or_request_id(http):
    client = AyInboxClient(TEST_KEY, http=http, max_retries=0)
    body = fixture("errors/429_category_rate_limited.json")
    http.add("GET", "/v1/suppressions", make_response(429, body, {"Content-Type": "application/json"}))
    with pytest.raises(errors.RateLimitError) as info:
        client.request("GET", "/suppressions")
    assert info.value.code == "rate_limit_exceeded"
    assert info.value.request_id is None
    assert info.value.retry_after == 12


def test_retry_after_header_wins(http):
    client = AyInboxClient(TEST_KEY, http=http, max_retries=0)
    http.add("GET", "/v1/me", error_response("429_api_key_rate_limited.json"))
    with pytest.raises(errors.RateLimitError) as info:
        client.request("GET", "/me")
    assert info.value.retry_after == 12


def test_non_json_error_body(http):
    client = AyInboxClient(TEST_KEY, http=http, max_retries=0)
    http.add("GET", "/v1/me", make_response(502, "Bad gateway", {"X-Request-Id": "edge-1"}))
    with pytest.raises(errors.InternalServerError) as info:
        client.request("GET", "/me")
    assert info.value.code == "http_error"
    assert info.value.message == "Bad gateway"
    assert info.value.request_id == "edge-1"


def test_retries_get_on_503_then_succeeds(client, http, sleeps):
    http.add("GET", "/v1/me", error_response("503_service_unavailable.json"), make_response(200, fixture("me.json")))
    assert client.request("GET", "/me")["user_id"]
    assert len(http.calls) == 2
    assert sleeps == [5.0]


def test_retries_429_honouring_retry_after(client, http, sleeps):
    http.add("GET", "/v1/me", error_response("429_api_key_rate_limited.json"), make_response(200, fixture("me.json")))
    client.request("GET", "/me")
    assert sleeps == [12.0]


def test_gives_up_after_max_retries(client, http):
    http.add("GET", "/v1/me", error_response("503_service_unavailable.json"))
    with pytest.raises(errors.ServiceUnavailableError):
        client.request("GET", "/me")
    assert len(http.calls) == 3


def test_does_not_retry_keyless_post_on_503(client, http):
    http.add("POST", "/v1/campaigns", error_response("503_service_unavailable.json"))
    with pytest.raises(errors.ServiceUnavailableError):
        client.request("POST", "/campaigns", body={"name": "x"})
    assert len(http.calls) == 1


def test_does_not_retry_keyless_patch_on_502(client, http):
    http.add("PATCH", "/v1/contacts/x", make_response(502, {"error": "Bad Gateway"}))
    with pytest.raises(errors.InternalServerError):
        client.request("PATCH", "/contacts/x", body={"first_name": "A"})
    assert len(http.calls) == 1


def test_retries_keyed_post_on_503(client, http):
    http.add(
        "POST",
        "/v1/campaigns",
        error_response("503_service_unavailable.json"),
        make_response(200, fixture("campaign.json")),
    )
    client.request("POST", "/campaigns", body={"name": "x"}, idempotency_key="k1")
    assert len(http.calls) == 2
    assert all(c["headers"]["Idempotency-Key"] == "k1" for c in http.calls)


def test_retries_keyless_post_on_429(client, http):
    http.add(
        "POST",
        "/v1/campaigns",
        error_response("429_api_key_rate_limited.json"),
        make_response(200, fixture("campaign.json")),
    )
    client.request("POST", "/campaigns", body={"name": "x"})
    assert len(http.calls) == 2


def test_read_only_post_retries(client, http):
    http.add(
        "POST",
        "/v1/contacts/search",
        error_response("503_service_unavailable.json"),
        make_response(200, fixture("contacts_list.json")),
    )
    client.request("POST", "/contacts/search", body={}, read_only=True)
    assert len(http.calls) == 2


def test_never_retries_idempotency_outcome_unknown(client, http):
    http.add("POST", "/v1/campaigns", error_response("409_idempotency_outcome_unknown.json"))
    with pytest.raises(errors.ConflictError):
        client.request("POST", "/campaigns", body={"name": "x"}, idempotency_key="k1")
    assert len(http.calls) == 1


def test_does_not_retry_500(client, http):
    http.add("GET", "/v1/me", error_response("500_internal_error.json"))
    with pytest.raises(errors.InternalServerError):
        client.request("GET", "/me")
    assert len(http.calls) == 1


def test_long_retry_after_is_returned_not_waited(client, http, sleeps):
    http.add("GET", "/v1/me", make_response(429, {"code": "rate_limit_exceeded"}, {"Retry-After": "90"}))
    with pytest.raises(errors.RateLimitError) as info:
        client.request("GET", "/me")
    assert info.value.retry_after == 90
    assert sleeps == []


def test_connection_error_retried_for_get(client, http):
    http.add("GET", "/v1/me", requests.ConnectionError("boom"), make_response(200, fixture("me.json")))
    client.request("GET", "/me")
    assert len(http.calls) == 2


def test_connection_error_not_retried_for_keyless_post(client, http):
    http.add("POST", "/v1/suppressions", requests.Timeout("slow"))
    with pytest.raises(errors.AyInboxConnectionError):
        client.request("POST", "/suppressions", body={"entries": []})
    assert len(http.calls) == 1
