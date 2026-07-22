from __future__ import annotations

from pathlib import Path


def test_debug_notion_blocks_script_prints_block_tree(monkeypatch, capsys) -> None:
    import scripts.debug_notion_blocks as script

    class FakeBlock:
        def __init__(self, block_id: str, block_type: str, text: str = "", has_children: bool = False, children=None):
            self.id = block_id
            self.type = block_type
            self.text = text
            self.has_children = has_children
            self.children = children or []

    called = {}

    def fake_create_notion_client():
        called["called"] = True
        return object()

    def fake_parse_block_tree(notion, page_id):
        called["page_id"] = page_id
        return [FakeBlock("block_1", "paragraph", "Hello", False)]

    monkeypatch.setattr(script, "create_notion_client", fake_create_notion_client)
    monkeypatch.setattr(script, "parse_block_tree", fake_parse_block_tree)

    exit_code = script.main(["11111111111111111111111111111111"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["called"] is True
    assert called["page_id"] == "11111111111111111111111111111111"
    assert '"count": 1' in output
    assert '"text": "Hello"' in output
