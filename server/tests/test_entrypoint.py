from opensandbox_plus.entrypoint import _env_enabled


def test_env_enabled_defaults_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("OSB_PLUS_TEST_FLAG", raising=False)

    assert _env_enabled("OSB_PLUS_TEST_FLAG", default=True) is True
    assert _env_enabled("OSB_PLUS_TEST_FLAG", default=False) is False


def test_env_enabled_parses_false_values(monkeypatch) -> None:
    for value in ("0", "false", "False", "no", "off"):
        monkeypatch.setenv("OSB_PLUS_TEST_FLAG", value)
        assert _env_enabled("OSB_PLUS_TEST_FLAG", default=True) is False


def test_env_enabled_treats_other_values_as_true(monkeypatch) -> None:
    for value in ("1", "true", "yes", "on", "anything"):
        monkeypatch.setenv("OSB_PLUS_TEST_FLAG", value)
        assert _env_enabled("OSB_PLUS_TEST_FLAG", default=False) is True
