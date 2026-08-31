from __future__ import annotations

import subprocess
import sys


def test_wizard_importable_as_first_module_standalone():
    """Regression: mika.cli.wizard used to import mika.ai.errors, which
    (via mika.ai/__init__.py -> mika.ai.providers -> gemini.py) transitively
    tried to import register_model_fetcher back from mika.cli.wizard --
    which, if wizard.py itself was the very first module touched in the
    process, was still only partially initialized (hadn't reached the
    register_model_fetcher definition yet), causing an ImportError.

    This only ever failed when wizard.py was the true first import in a
    fresh process (not from within the same pytest session, since some
    other test module had usually already fully loaded
    mika.ai.providers.gemini first) -- so it's tested here via a genuinely
    fresh subprocess rather than an in-process import.
    """
    result = subprocess.run(
        [sys.executable, "-c", "from mika.cli.wizard import _ask"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_register_model_fetcher_lives_in_provider_registry_not_wizard():
    """The registry (display names + fetchers + decorator) was moved out of
    wizard.py into mika.ai.provider_registry specifically to break the
    wizard.py <-> gemini.py circular import. wizard.py re-exports the same
    objects (not copies) for backward compatibility."""
    from mika.ai import provider_registry
    from mika.cli import wizard

    assert wizard._MODEL_FETCHERS is provider_registry._MODEL_FETCHERS
    assert wizard._PROVIDER_DISPLAY_NAMES is provider_registry._PROVIDER_DISPLAY_NAMES
    assert wizard.register_model_fetcher is provider_registry.register_model_fetcher


def test_gemini_registers_via_provider_registry_not_wizard():
    from mika.ai.providers import gemini

    assert "from mika.cli.wizard import register_model_fetcher" not in open(gemini.__file__).read()
