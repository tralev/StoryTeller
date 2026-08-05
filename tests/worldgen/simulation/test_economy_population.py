from src.worldgen.artifacts import WorldArtifactRepository


def test_population_cohorts_and_goods_remain_conserved_and_nonnegative(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    snapshots = repository.load_verified("snapshots").payload
    for snapshot in snapshots:
        state = snapshot["state"]
        cohort_totals = {}
        for cohort in state["cohorts"]:
            cohort_totals[cohort["civilization_id"]] = cohort_totals.get(cohort["civilization_id"], 0) + cohort["population"]
        assert all(civilization["population"] == cohort_totals[civilization["civilization_id"]]
                   for civilization in state["civilizations"])
        assert all(civilization["population"] >= 0 and civilization["economy"]["grain"] >= 0
                   and civilization["economy"]["currency"] >= 0
                   for civilization in state["civilizations"])


def test_trade_and_migration_are_balanced(simulated_world):
    _, historical, _ = simulated_world
    history = WorldArtifactRepository(historical / "artifacts").load_verified("history").payload
    for event in history:
        if event["kind"] == "trade":
            assert sum(c["amount"] for c in event["consequences"] if c["kind"] == "grain_delta") == 0
            assert sum(c["amount"] for c in event["consequences"] if c["kind"] == "currency_delta") == 0
        if event["kind"] == "migration":
            assert sum(c["amount"] for c in event["consequences"] if c["kind"] == "population_delta") == 0
