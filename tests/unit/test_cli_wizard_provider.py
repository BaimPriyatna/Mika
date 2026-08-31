from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mika.ai.errors import AIAuthenticationError, AIProviderError
from mika.cli import wizard
from mika.cli.wizard import WizardCancelled


@pytest.fixture(autouse=True)
def _restore_fetchers():
    original = dict(wizard._MODEL_FETCHERS)
    yield
    wizard._MODEL_FETCHERS.clear()
    wizard._MODEL_FETCHERS.update(original)


class TestRunProviderWizard:
    @pytest.mark.asyncio
    async def test_happy_path_returns_every_fetched_model(self):
        wizard._MODEL_FETCHERS["gemini"] = AsyncMock(
            return_value=["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]
        )

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch("mika.cli.wizard.env_secrets.set_provider_secret") as mock_set_secret,
        ):
            mock_select.side_effect = [_asked("gemini")]
            mock_password.return_value = _asked("real-key")

            provider, models = await wizard.run_provider_wizard()

        assert provider == "gemini"
        assert models == ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]
        wizard._MODEL_FETCHERS["gemini"].assert_awaited_once_with("real-key")
        mock_set_secret.assert_called_once_with("gemini", "real-key")
        assert mock_select.call_count == 1

    @pytest.mark.asyncio
    async def test_does_not_ask_which_model_to_activate(self):
        wizard._MODEL_FETCHERS["gemini"] = AsyncMock(return_value=["only-this-model"])

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch("mika.cli.wizard.env_secrets.set_provider_secret"),
        ):
            mock_select.side_effect = [_asked("gemini")]
            mock_password.return_value = _asked("real-key")

            provider, models = await wizard.run_provider_wizard()

        assert models == ["only-this-model"]
        assert mock_select.call_count == 1

    @pytest.mark.asyncio
    async def test_rejected_key_reprompts_instead_of_giving_up(self):
        wizard._MODEL_FETCHERS["gemini"] = AsyncMock(
            side_effect=[AIAuthenticationError("bad key"), ["gemini-1.5-flash"]]
        )

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch("mika.cli.wizard.questionary.confirm") as mock_confirm,
            patch("mika.cli.wizard.env_secrets.set_provider_secret"),
        ):
            mock_select.side_effect = [_asked("gemini")]
            mock_password.side_effect = [_asked("wrong-key"), _asked("right-key")]
            mock_confirm.return_value = _asked(True)

            provider, models = await wizard.run_provider_wizard()

        assert provider == "gemini"
        assert models == ["gemini-1.5-flash"]
        assert wizard._MODEL_FETCHERS["gemini"].await_count == 2

    @pytest.mark.asyncio
    async def test_declining_retry_after_rejected_key_cancels(self):
        wizard._MODEL_FETCHERS["gemini"] = AsyncMock(side_effect=AIAuthenticationError("bad key"))

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch("mika.cli.wizard.questionary.confirm") as mock_confirm,
        ):
            mock_select.side_effect = [_asked("gemini")]
            mock_password.return_value = _asked("wrong-key")
            mock_confirm.return_value = _asked(False)

            with pytest.raises(WizardCancelled):
                await wizard.run_provider_wizard()

    @pytest.mark.asyncio
    async def test_non_auth_fetch_failure_falls_back_to_single_manual_model(self):
        wizard._MODEL_FETCHERS["gemini"] = AsyncMock(side_effect=AIProviderError("network blip"))

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch("mika.cli.wizard.questionary.confirm") as mock_confirm,
            patch("mika.cli.wizard.questionary.text") as mock_text,
            patch("mika.cli.wizard.env_secrets.set_provider_secret"),
        ):
            mock_select.side_effect = [_asked("gemini")]
            mock_password.return_value = _asked("real-key")
            mock_confirm.return_value = _asked(True)
            mock_text.return_value = _asked("gemini-custom-model")

            provider, models = await wizard.run_provider_wizard()

        assert provider == "gemini"
        assert models == ["gemini-custom-model"]

    @pytest.mark.asyncio
    async def test_returns_models_even_when_env_file_persist_fails(self):
        wizard._MODEL_FETCHERS["gemini"] = AsyncMock(return_value=["gemini-2.5-flash"])

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch(
                "mika.cli.wizard.env_secrets.set_provider_secret",
                side_effect=wizard.env_secrets.EnvFileError("read-only filesystem"),
            ),
        ):
            mock_select.side_effect = [_asked("gemini")]
            mock_password.return_value = _asked("real-key")

            provider, models = await wizard.run_provider_wizard()

        assert provider == "gemini"
        assert models == ["gemini-2.5-flash"]


class TestSelectModelAddFlow:

    @pytest.mark.asyncio
    async def test_single_fetched_model_auto_selected_without_extra_prompt(self):
        from mika.cli.config import AppConfig

        wizard._MODEL_FETCHERS["gemini"] = AsyncMock(return_value=["only-model"])
        config = AppConfig()

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch("mika.cli.wizard.env_secrets.set_provider_secret"),
        ):
            mock_select.side_effect = [_asked("__add__"), _asked("gemini")]
            mock_password.return_value = _asked("real-key")

            result = await wizard.select_model(config)

        assert result == ("gemini", "only-model")
        assert config.models[0].provider == "gemini"
        assert config.models[0].model == "only-model"

    @pytest.mark.asyncio
    async def test_multiple_fetched_models_prompts_for_one(self):
        from mika.cli.config import AppConfig

        wizard._MODEL_FETCHERS["gemini"] = AsyncMock(return_value=["model-a", "model-b"])
        config = AppConfig()

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch("mika.cli.wizard.env_secrets.set_provider_secret"),
        ):
            mock_select.side_effect = [_asked("__add__"), _asked("gemini"), _asked("model-b")]
            mock_password.return_value = _asked("real-key")

            result = await wizard.select_model(config)

        assert result == ("gemini", "model-b")
        assert {m.model for m in config.models} == {"model-a", "model-b"}


class TestProviderRegistry:
    """Verifies the production registration path itself -- these tests must
    fail if @register_model_fetcher("gemini", ...) is ever removed from
    gemini.py, without relying on any manual injection into _MODEL_FETCHERS."""

    def test_gemini_fetcher_registered_via_real_production_import(self):
        # Import the real module -- this is what triggers the decorator in
        # production. No mocking/injection involved.
        from mika.ai.providers.gemini import list_models as real_list_models

        assert wizard._MODEL_FETCHERS.get("gemini") is real_list_models
        assert wizard._PROVIDER_DISPLAY_NAMES.get("gemini") == "Google Gemini"

    def test_provider_without_fetcher_is_not_selectable(self):
        # "openai" is declared for display but has no registered fetcher
        # (no module registers it yet) -- it must show up disabled, never
        # selectable, in the picker.
        choices = {c.value: c for c in wizard._provider_choices()}
        assert "openai" in choices
        assert choices["openai"].disabled

    def test_provider_with_fetcher_is_selectable(self):
        from mika.ai.providers.gemini import list_models  # noqa: F401  (ensures registration)

        choices = {c.value: c for c in wizard._provider_choices()}
        assert "gemini" in choices
        assert not choices["gemini"].disabled

    def test_no_choice_can_be_selectable_without_a_registered_fetcher(self):
        """Structural invariant: every non-disabled choice must correspond
        to an entry in _MODEL_FETCHERS. This is guaranteed by construction
        (_provider_choices derives 'disabled' from _MODEL_FETCHERS
        membership), but this test pins that invariant so a future refactor
        can't silently reintroduce a second, independently-settable
        availability flag."""
        for choice in wizard._provider_choices():
            if not choice.disabled:
                assert choice.value in wizard._MODEL_FETCHERS


class TestExistingApiKeyFlow:
    @pytest.mark.asyncio
    async def test_use_existing_key_skips_password_prompt_and_does_not_rewrite_secret(self):
        wizard._MODEL_FETCHERS["gemini"] = AsyncMock(return_value=["gemini-1.5-flash"])

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch("mika.cli.wizard.env_secrets.get_provider_secret", return_value="old-key"),
            patch("mika.cli.wizard.env_secrets.set_provider_secret") as mock_set_secret,
        ):
            mock_select.side_effect = [_asked("gemini"), _asked("use")]

            provider, models = await wizard.run_provider_wizard()

        assert provider == "gemini"
        assert models == ["gemini-1.5-flash"]
        mock_password.assert_not_called()
        mock_set_secret.assert_not_called()
        wizard._MODEL_FETCHERS["gemini"].assert_awaited_once_with("old-key")

    @pytest.mark.asyncio
    async def test_replace_key_only_persists_new_key_after_successful_fetch(self):
        wizard._MODEL_FETCHERS["gemini"] = AsyncMock(return_value=["gemini-1.5-pro"])

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch("mika.cli.wizard.env_secrets.get_provider_secret", return_value="old-key"),
            patch("mika.cli.wizard.env_secrets.set_provider_secret") as mock_set_secret,
        ):
            mock_select.side_effect = [_asked("gemini"), _asked("replace")]
            mock_password.return_value = _asked("new-key")

            provider, models = await wizard.run_provider_wizard()

        assert provider == "gemini"
        assert models == ["gemini-1.5-pro"]
        wizard._MODEL_FETCHERS["gemini"].assert_awaited_once_with("new-key")
        mock_set_secret.assert_called_once_with("gemini", "new-key")

    @pytest.mark.asyncio
    async def test_replace_key_invalid_leaves_old_key_untouched(self):
        """If the new key is rejected and the user declines to retry, the old
        key must never have been deleted or overwritten (set_provider_secret
        must never be called)."""
        wizard._MODEL_FETCHERS["gemini"] = AsyncMock(side_effect=AIAuthenticationError("bad key"))

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch("mika.cli.wizard.questionary.confirm") as mock_confirm,
            patch("mika.cli.wizard.env_secrets.get_provider_secret", return_value="old-key"),
            patch("mika.cli.wizard.env_secrets.set_provider_secret") as mock_set_secret,
        ):
            mock_select.side_effect = [_asked("gemini"), _asked("replace")]
            mock_password.return_value = _asked("bad-new-key")
            mock_confirm.return_value = _asked(False)  # decline retry

            with pytest.raises(WizardCancelled):
                await wizard.run_provider_wizard()

        mock_set_secret.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_leaves_old_key_untouched(self):
        wizard._MODEL_FETCHERS["gemini"] = AsyncMock()

        with (
            patch("mika.cli.wizard.questionary.select") as mock_select,
            patch("mika.cli.wizard.questionary.password") as mock_password,
            patch("mika.cli.wizard.env_secrets.get_provider_secret", return_value="old-key"),
            patch("mika.cli.wizard.env_secrets.set_provider_secret") as mock_set_secret,
        ):
            mock_select.side_effect = [_asked("gemini"), _asked("cancel")]

            with pytest.raises(WizardCancelled):
                await wizard.run_provider_wizard()

        mock_password.assert_not_called()
        mock_set_secret.assert_not_called()
        wizard._MODEL_FETCHERS["gemini"].assert_not_awaited()


def _asked(value):
    q = AsyncMock()
    q.ask_async = AsyncMock(return_value=value)
    # _ask() (wizard.py) registers an Escape-cancels binding via
    # question.application.key_bindings.add(...) before calling
    # ask_async() -- give the mock a plain (non-async) callable chain for
    # that, since it's synchronous in real usage (KeyBindings.add returns a
    # decorator, called immediately with the handler function).
    q.application = Mock()
    q.application.key_bindings.add = Mock(return_value=Mock())
    return q
