import json
import subprocess
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
    evidence = json.loads((ROOT / "docs/evidence/mcp-host/generated-package.json").read_text())
    assert {"apps": apps["apps"]} == evidence["generated_app_mapping"]
    for name in ("icon.svg", "district-report.png", "comparison.png"):
        assert (package / "assets" / name).is_file()


def test_package_validator_rejects_bad_identity_endpoint_and_references(tmp_path):
    source = ROOT / "plugin"
    package = tmp_path / "plugin"
    import shutil
    shutil.copytree(source, package)
    evidence_dir = tmp_path / "docs/evidence/mcp-host"
    evidence_dir.mkdir(parents=True)
    shutil.copy(ROOT / "docs/evidence/mcp-host/generated-package.json", evidence_dir / "generated-package.json")
    validator = ROOT / "tests/plugin/validate.mjs"
    def invalid(name, mutator):
        target = tmp_path / name
        shutil.copytree(package, target)
        positive = subprocess.run(["node", str(validator), str(target)], capture_output=True, text=True)
        assert positive.returncode == 0, positive.stderr
        mutator(target)
        run = subprocess.run(["node", str(validator), str(target)], capture_output=True, text=True)
        assert run.returncode != 0
    invalid("fabricated-id", lambda root: (root / ".app.json").write_text(
        json.dumps({"apps": {"dev-deadbeef": {"id": "asdk_app_deadbeef"}}})
    ))
    invalid("bad-endpoint", lambda root: (root / "mcp.json").write_text(
        json.dumps({"mcpServers": {"x": {"type": "streamable-http", "url": "http://evil.test/mcp"}}})
    ))
    invalid("missing-asset", lambda root: (root / "assets/district-report.png").unlink())
    invalid("headers", lambda root: (root / "mcp.json").write_text(json.dumps({
        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        "mcpServers": {
            "texas-isd-finances": {
                "type": "streamable-http", "url": "https://txisd.dev/mcp", "headers": {"Authorization": "x"},
            }
        },
    })))
    def add_unknown(root):
        manifest = json.loads((root / "plugin.json").read_text())
        manifest["unknown"] = True
        (root / "plugin.json").write_text(json.dumps(manifest))
    invalid("unsupported", add_unknown)
    def traversal(root):
        manifest = json.loads((root / "plugin.json").read_text())
        interface = manifest["extensions"]["com.openai"]["interface"]
        interface["screenshots"] = ["./../outside.png", "./assets/comparison.png"]
        (root / "plugin.json").write_text(json.dumps(manifest))
    invalid("traversal", traversal)
