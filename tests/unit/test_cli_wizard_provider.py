from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
            patch("mika.cli.wizard.env_secrets.ensure_gitignored", return_value=False),
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
            patch("mika.cli.wizard.env_secrets.ensure_gitignored", return_value=False),
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
            patch("mika.cli.wizard.env_secrets.ensure_gitignored", return_value=False),
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
            patch("mika.cli.wizard.env_secrets.ensure_gitignored", return_value=False),
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
            patch("mika.cli.wizard.env_secrets.ensure_gitignored", return_value=False),
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
            patch("mika.cli.wizard.env_secrets.ensure_gitignored", return_value=False),
        ):
            mock_select.side_effect = [_asked("__add__"), _asked("gemini"), _asked("model-b")]
            mock_password.return_value = _asked("real-key")

            result = await wizard.select_model(config)

        assert result == ("gemini", "model-b")
        assert {m.model for m in config.models} == {"model-a", "model-b"}


def _asked(value):
    q = AsyncMock()
    q.ask_async = AsyncMock(return_value=value)
    return q
