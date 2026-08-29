"""Desktop Forge memory policy must stay synchronized with its roadmap contract."""

from pathlib import Path

from scripts.run_with_memory_cap import DESKTOP_HARD_GB, DESKTOP_SOFT_GB


def test_desktop_forge_uses_16_gib_host_guard() -> None:
    assert (DESKTOP_SOFT_GB, DESKTOP_HARD_GB) == (11.0, 12.0)


def test_roadmap_publishes_same_desktop_guard_without_changing_mobile() -> None:
    roadmap = (Path(__file__).resolve().parents[1] / "docs/roadmap.md").read_text()
    assert "soft stop at 11 GiB" in roadmap
    assert "hard ceiling 12 GiB" in roadmap
    assert "does not alter phone-side budgets" in roadmap
