"""Tests for Prompt Learning link resolver."""

from testcase_agent.prompt_learning.resolve_links import resolve_links, _parse_link_keys
from testcase_agent.prompt_learning.contracts import (
    ParsedRequirement,
    ParsedRefTestCase,
)


def make_req(key: str, desc: str = "", req_type: str = "requirement") -> ParsedRequirement:
    return ParsedRequirement(
        requirement_key=key,
        description=desc or f"Desc of {key}",
        requirement_type=req_type,
    )


def make_case(
    case_id: str,
    linked_raw: str,
    source_sheet: str = "Cases",
    source_row: int = 2,
    title: str = "",
) -> ParsedRefTestCase:
    return ParsedRefTestCase(
        case_id=case_id,
        case_id_generated=False,
        linked_requirements_raw=linked_raw,
        linked_requirement_keys=[],
        title=title or f"Title {case_id}",
        title_missing=False,
        action="Test action",
        expected_result="Test expected",
        source_sheet=source_sheet,
        source_row=source_row,
    )


class TestLinkKeyParsing:
    def test_newline_separator(self):
        assert _parse_link_keys("REQ-1\nREQ-2") == ["REQ-1", "REQ-2"]

    def test_comma_separator(self):
        assert _parse_link_keys("REQ-1, REQ-2") == ["REQ-1", "REQ-2"]

    def test_semicolon_separator(self):
        assert _parse_link_keys("REQ-1;REQ-2") == ["REQ-1", "REQ-2"]

    def test_chinese_comma(self):
        assert _parse_link_keys("REQ-1，REQ-2") == ["REQ-1", "REQ-2"]

    def test_chinese_semicolon(self):
        assert _parse_link_keys("REQ-1；REQ-2") == ["REQ-1", "REQ-2"]

    def test_mixed_separators(self):
        assert _parse_link_keys("REQ-1, REQ-2\nREQ-3;REQ-4") == [
            "REQ-1", "REQ-2", "REQ-3", "REQ-4",
        ]

    def test_single_key(self):
        assert _parse_link_keys("REQ-1") == ["REQ-1"]

    def test_empty_string(self):
        assert _parse_link_keys("") == []

    def test_trims_whitespace(self):
        assert _parse_link_keys("  REQ-1 ,  REQ-2  ") == ["REQ-1", "REQ-2"]


class TestResolveLinks:
    def test_basic_linking(self):
        reqs = [make_req("REQ-1"), make_req("REQ-2")]
        cases = [make_case("TC-1", "REQ-1"), make_case("TC-2", "REQ-2")]
        links, style, no_test, issues, summary = resolve_links(reqs, cases)
        assert len(links) == 2
        assert all(l.resolved for l in links)
        assert summary.valid_link_count == 2
        assert style == []
        assert no_test == []

    def test_multi_link_case(self):
        """One case linked to multiple Requirements."""
        reqs = [make_req("REQ-1"), make_req("REQ-2")]
        cases = [make_case("TC-1", "REQ-1\nREQ-2")]
        links, style, no_test, issues, summary = resolve_links(reqs, cases)
        assert len(links) == 2
        assert links[0].requirement_key == "REQ-1"
        assert links[1].requirement_key == "REQ-2"
        assert summary.valid_link_count == 2

    def test_multi_case_same_requirement(self):
        """Multiple cases linked to one Requirement (normal)."""
        reqs = [make_req("REQ-1")]
        cases = [
            make_case("TC-1", "REQ-1", source_row=2),
            make_case("TC-2", "REQ-1", source_row=3),
        ]
        links, style, no_test, issues, summary = resolve_links(reqs, cases)
        assert len(links) == 2
        assert all(l.requirement_key == "REQ-1" for l in links)
        assert summary.valid_link_count == 2

    def test_unknown_link(self):
        reqs = [make_req("REQ-1")]
        cases = [make_case("TC-1", "REQ-1\nREQ-UNKNOWN")]
        links, style, no_test, issues, summary = resolve_links(reqs, cases)
        assert len(links) == 2
        resolved = [l for l in links if l.resolved]
        unresolved = [l for l in links if not l.resolved]
        assert len(resolved) == 1
        assert resolved[0].requirement_key == "REQ-1"
        assert len(unresolved) == 1
        assert unresolved[0].requirement_key == "REQ-UNKNOWN"
        assert any(i.issue_type == "unknown_requirement_link" for i in issues)

    def test_all_links_unknown(self):
        reqs = [make_req("REQ-1")]
        cases = [make_case("TC-1", "REQ-UNKNOWN")]
        links, style, no_test, issues, summary = resolve_links(reqs, cases)
        assert len(links) == 1
        assert not links[0].resolved
        # All-orphan case → style-only
        assert len(style) == 1
        assert style[0].case_id == "TC-1"
        assert any(i.issue_type == "all_links_unknown" for i in issues)

    def test_no_links_style_only(self):
        reqs = [make_req("REQ-1")]
        cases = [make_case("TC-1", "")]
        links, style, no_test, issues, summary = resolve_links(reqs, cases)
        assert links == []
        assert len(style) == 1
        assert style[0].case_id == "TC-1"
        assert any(i.issue_type == "missing_links" for i in issues)

    def test_no_test_requirements(self):
        reqs = [make_req("REQ-1"), make_req("REQ-2")]
        cases = [make_case("TC-1", "REQ-1")]
        links, style, no_test, issues, summary = resolve_links(reqs, cases)
        assert len(no_test) == 1
        assert no_test[0].requirement_key == "REQ-2"
        assert summary.no_test_requirement_count == 1

    def test_heading_rows_become_no_test(self):
        """Heading/info rows with no links become No-Test Requirements."""
        reqs = [
            make_req("HD-1", "A heading", "heading"),
            make_req("REQ-1", "Real requirement"),
        ]
        cases = [make_case("TC-1", "REQ-1")]
        links, style, no_test, issues, summary = resolve_links(reqs, cases)
        assert len(no_test) == 1
        assert no_test[0].requirement_key == "HD-1"

    def test_explicit_links_take_precedence(self):
        """Even heading rows with explicit links are treated as linked."""
        reqs = [
            make_req("HD-1", "A heading", "heading"),
            make_req("REQ-1", "Real requirement"),
        ]
        cases = [make_case("TC-1", "HD-1")]
        links, style, no_test, issues, summary = resolve_links(reqs, cases)
        # HD-1 has a link → not a No-Test Requirement
        assert len(no_test) == 1
        assert no_test[0].requirement_key == "REQ-1"
        assert links[0].requirement_key == "HD-1"

    def test_summary_counts(self):
        reqs = [make_req("REQ-1"), make_req("REQ-2"), make_req("REQ-3")]
        cases = [
            make_case("TC-1", "REQ-1", source_row=2),
            make_case("TC-2", "", source_row=3),  # no links
            make_case("TC-3", "REQ-UNKNOWN", source_row=4),  # all unknown
        ]
        links, style, no_test, issues, summary = resolve_links(reqs, cases)
        assert summary.requirement_count == 3
        assert summary.ref_test_case_count == 3
        assert summary.valid_link_count == 1  # only REQ-1 -> TC-1 resolved
        assert summary.no_test_requirement_count == 2  # REQ-2, REQ-3
        assert summary.style_only_case_count == 2  # TC-2 and TC-3
        assert summary.data_issue_count > 0
