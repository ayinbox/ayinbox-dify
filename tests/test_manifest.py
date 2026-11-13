"""Checks the plugin's YAML the way the Marketplace reviewers and the Dify loader read it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from conftest import ROOT

from ayinbox_api.client import USER_AGENT, VERSION

YAML_FILES = sorted(
    p for p in ROOT.rglob("*.y*ml") if not any(part.startswith(".") for part in p.relative_to(ROOT).parts)
)
MARKETPLACE_TAGS = {
    "agent",
    "business",
    "design",
    "education",
    "entertainment",
    "finance",
    "image",
    "news",
    "other",
    "productivity",
    "rag",
    "search",
    "social",
    "travel",
    "utilities",
    "videos",
    "weather",
}


def load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", YAML_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_yaml_parses(path):
    assert load(path) is not None


def test_manifest_required_fields():
    m = load(ROOT / "manifest.yaml")
    for dotted in (
        "author",
        "name",
        "version",
        "type",
        "icon",
        "plugins",
        "privacy",
        "repo",
        "contact",
        "label.en_US",
        "label.zh_Hans",
        "description.en_US",
        "description.zh_Hans",
        "meta.version",
        "meta.arch",
        "meta.runner.language",
        "meta.runner.version",
        "meta.runner.entrypoint",
        "meta.minimum_dify_version",
        "resource.memory",
        "created_at",
        "tags",
    ):
        node = m
        for key in dotted.split("."):
            assert isinstance(node, dict) and key in node, f"manifest.yaml is missing {dotted}"
            node = node[key]
        assert node not in (None, "", []), f"manifest.yaml has an empty {dotted}"
    assert m["author"] == "ayinbox" and m["name"] == "ayinbox" and m["type"] == "plugin"
    assert "dify" not in m["author"] and "langgenius" not in m["author"]
    assert m["version"] == VERSION and USER_AGENT.endswith(VERSION)
    assert re.match(r"^https://github\.com/ayinbox/ayinbox-dify$", m["repo"])
    assert m["contact"] == "team@ayinbox.com"
    assert set(m["tags"]) <= MARKETPLACE_TAGS and 1 <= len(m["tags"]) <= 3
    assert m["network"]["domains"] == ["api.ayinbox.com"]
    assert (ROOT / "_assets" / m["icon"]).is_file()
    assert (ROOT / m["privacy"]).is_file()
    assert m["meta"]["runner"]["entrypoint"] == "main" and (ROOT / "main.py").is_file()
    for provider in m["plugins"]["tools"]:
        assert (ROOT / provider).is_file()


def test_requirements_pin_dify_plugin():
    lines = [line.strip() for line in (ROOT / "requirements.txt").read_text().splitlines() if line.strip()]
    assert any(re.match(r"^dify_plugin==\d+\.\d+\.\d+$", line) for line in lines)
    assert all("==" in line for line in lines)


def test_icon_is_custom_svg():
    svg = (ROOT / "_assets" / "icon.svg").read_text()
    assert svg.lstrip().startswith("<svg") and "#0ea5e9" in svg
    assert "DIFY_MARKETPLACE_TEMPLATE_ICON_DO_NOT_USE" not in svg


def i18n_ok(node) -> bool:
    return isinstance(node, dict) and bool(node.get("en_US")) and bool(node.get("zh_Hans"))


def test_provider_and_tools():
    provider = load(ROOT / "provider" / "ayinbox.yaml")
    ident = provider["identity"]
    assert ident["author"] == "ayinbox" and ident["name"] == "ayinbox"
    assert i18n_ok(ident["label"]) and i18n_ok(ident["description"])
    assert (ROOT / "_assets" / ident["icon"]).is_file()
    creds = provider["credentials_for_provider"]
    assert list(creds) == ["api_key"]
    assert creds["api_key"]["type"] == "secret-input" and creds["api_key"]["required"] is True
    assert (ROOT / provider["extra"]["python"]["source"]).is_file()

    listed = provider["tools"]
    on_disk = sorted(f"tools/{p.name}" for p in (ROOT / "tools").glob("*.yaml"))
    assert sorted(listed) == on_disk
    for rel in listed:
        tool = load(ROOT / rel)
        name = Path(rel).stem
        assert tool["identity"]["name"] == name and tool["identity"]["author"] == "ayinbox"
        assert i18n_ok(tool["identity"]["label"])
        assert i18n_ok(tool["description"]["human"]) and len(tool["description"]["llm"]) > 40
        assert tool["extra"]["python"]["source"] == f"tools/{name}.py"
        assert (ROOT / "tools" / f"{name}.py").is_file()
        for param in tool.get("parameters") or []:
            assert param["type"] in {"string", "number", "boolean", "select"}, (name, param["name"])
            assert param["form"] in {"llm", "form"}
            assert i18n_ok(param["label"]) and i18n_ok(param["human_description"]), (name, param["name"])
            assert param.get("llm_description"), (name, param["name"])
            if param["type"] == "select":
                assert all(i18n_ok(o["label"]) for o in param["options"])
                assert param.get("default") in {o["value"] for o in param["options"]}


def test_paginated_tools_take_cursor_and_limit():
    for name in (
        "list_campaigns",
        "search_contacts",
        "list_mailboxes",
        "list_threads",
        "get_thread",
        "list_suppressions",
    ):
        params = {p["name"] for p in load(ROOT / "tools" / f"{name}.yaml")["parameters"]}
        assert {"cursor", "limit"} <= params, name


def test_package_excludes_development_files():
    ignored = (ROOT / ".difyignore").read_text().split()
    for pattern in (".git/**", ".venv/**", ".tools/**", "tests/**", ".github/**", "**/__pycache__/**"):
        assert pattern in ignored


def test_dify_loader_accepts_the_plugin(monkeypatch):
    from dify_plugin.config.config import DifyPluginEnv
    from dify_plugin.core.plugin_registration import PluginRegistration

    monkeypatch.chdir(ROOT)
    registration = PluginRegistration(DifyPluginEnv())
    assert registration.configuration.name == "ayinbox"
    [provider] = registration.tools_configuration
    names = [tool.identity.name for tool in provider.tools]
    assert names == [Path(rel).stem for rel in load(ROOT / "provider" / "ayinbox.yaml")["tools"]]
    assert set(registration.tools_mapping) == {"ayinbox"}
