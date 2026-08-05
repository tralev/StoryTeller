from scripts.check_workspace_hygiene import violations


def test_generated_state_is_confined_to_tmp() -> None:
    assert violations() == []
