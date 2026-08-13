from ashare_data.agent_cli.main import build_parser


def test_root_help_contains_copyable_examples() -> None:
    help_text = build_parser().format_help()

    assert "aasource quotes SH600519 SZ000001 --pretty" in help_text
    assert "aasource bars SH600036 --tf 1d --limit 5 --pretty" in help_text
    assert "aasource catalog --pretty" in help_text
