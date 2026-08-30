from src.storage.package_v2 import PackageV2Error, V2PackageBuilder


def test_failed_acceptance_does_not_publish(tmp_path) -> None:
    destination = tmp_path / "bad.story"
    builder = V2PackageBuilder("bad", 1, "node_00000000000000000000000000000001")
    try:
        builder.write(destination, node_assets={}, region_maps={})
    except PackageV2Error:
        pass
    assert not destination.exists()
    assert not (tmp_path / "bad.story.staging").exists()
