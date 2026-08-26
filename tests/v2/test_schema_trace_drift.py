from scripts.generate_schema_trace import TRACE_PATH, build_trace


def test_schema_trace_document_matches_generator() -> None:
    assert TRACE_PATH.is_file()
    assert TRACE_PATH.read_text() == build_trace()
