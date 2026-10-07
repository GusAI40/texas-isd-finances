import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_portable_package_uses_public_endpoint_and_creator_mapping():
    package = ROOT / "plugin"
    manifest = json.loads((package / "plugin.json").read_text())
    mcp = json.loads((package / "mcp.json").read_text())
    apps = json.loads((package / ".app.json").read_text())
    assert manifest["extensions"]["com.openai"]["apps"] == "./.app.json"
    assert mcp["mcpServers"]["texas-isd-finances"] == {"type": "streamable-http", "url": "https://txisd.dev/mcp"}
    assert len(apps["apps"]) == 1
