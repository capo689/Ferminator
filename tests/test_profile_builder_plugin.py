from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from ferminator.profiles import load_profile

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins" / "ferminator-profile-builder"
SKILL = PLUGIN / "skills" / "ferminator-profile-builder"
VALIDATOR_PATH = SKILL / "scripts" / "validate_profile.py"


def _validator_module():
    spec = spec_from_file_location("ferminator_profile_validator", VALIDATOR_PATH)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plugin_profile_validator_accepts_real_ferminator_profile():
    validator = _validator_module()
    profile_path = ROOT / "profiles" / "adam-cagle.md"

    assert validator.validate_profile_text(profile_path.read_text(encoding="utf-8")) == []
    assert load_profile(profile_path).profile.slug == "adam-cagle"


def test_plugin_profile_validator_rejects_unfinished_template():
    validator = _validator_module()
    template = (SKILL / "assets" / "profile-template.md").read_text(encoding="utf-8")

    errors = validator.validate_profile_text(template)

    assert any("unresolved placeholder" in error for error in errors)


def test_plugin_contains_no_scaffold_placeholders():
    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    manifest_text = (PLUGIN / ".codex-plugin" / "plugin.json").read_text(
        encoding="utf-8"
    )

    assert "[TODO:" not in skill_text
    assert "[TODO:" not in manifest_text
