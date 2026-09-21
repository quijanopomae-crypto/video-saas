from pathlib import Path
import importlib.util


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_no_secrets.py"
SPEC = importlib.util.spec_from_file_location("check_no_secrets", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_known_secret_formats_are_detected_without_real_credentials():
    samples = [
        "sk-" + "A" * 24,
        "AKIA" + "B" * 16,
        "gh" + "p_" + "C" * 36,
        "glpat-" + "D" * 24,
        "xox" + "b-" + "E" * 24,
        "AIza" + "F" * 35,
        "hf_" + "G" * 32,
        "sk_" + "live_" + "H" * 24,
        "-----BEGIN " + "PRIVATE KEY-----",
        "eyJ" + "I" * 12 + "." + "J" * 12 + "." + "K" * 12,
    ]
    for sample in samples:
        assert MODULE.scan_text(sample), sample


def test_generic_secret_assignment_is_detected():
    text = "AUTH_" + "TOKEN=" + "Z" * 32
    findings = MODULE.scan_text(text)
    assert any(item.startswith("generic_") for item in findings)


def test_clear_placeholders_do_not_fail_generic_assignment_rule():
    text = "JWT_" + "SECRET=" + "test-only-not-valid-for-production-0123456789"
    assert MODULE.scan_text(text) == []


def test_tracked_env_files_are_rejected_but_examples_are_allowed():
    assert MODULE.is_forbidden_env_path(".env")
    assert MODULE.is_forbidden_env_path("apps/api/.env.production")
    assert not MODULE.is_forbidden_env_path(".env.example")
    assert not MODULE.is_forbidden_env_path("apps/api/.env.sample")
