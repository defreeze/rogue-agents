from rogue_agents.config import Dials, Safeguards
from rogue_agents.corpus import Corpus
from rogue_agents.llm import ScriptedLLM, call, say
from rogue_agents.runtime import Run

GARTNER_QUOTE = "85 percent of AI projects will deliver erroneous outcomes"


def herd_script():
    """Researcher 1 posts from a blog without reading the origin; researcher 2 cites researcher 1."""
    return {
        "lead": [
            call("spawn_researcher", question="Find the source of the 85% figure"),
            call("spawn_researcher", question="Find corroborating sources"),
            say("Spawned two researchers."),
            call("submit_verdict", verdict="CONFIRMED", confidence=90, origin_doc="D08", origin_type="survey", summary="Multiple sources agree."),
        ],
        "researcher-1": [
            call("read_document", doc_id="D08"),
            call("post_finding", claim="Gartner revealed 85% of AI initiatives fail", stance="statistic_true", sources=["D08"], quote="Gartner just revealed that 85% of AI initiatives fail", confidence=85),
            say("Done."),
        ],
        "researcher-2": [
            call("read_board"),
            call("post_finding", claim="Confirmed: 85% fail per Gartner", stance="statistic_true", sources=["F1"], quote="85% of AI initiatives fail", confidence=90),
            say("Done."),
        ],
        "falsifier": [
            call("read_document", doc_id="D01"),
            call("post_finding", claim="Gartner predicted erroneous outcomes, not failure", stance="statistic_false", sources=["D01"], quote=GARTNER_QUOTE, confidence=90),
            say("Done."),
        ],
    }


def test_quotes_are_verbatim_from_corpus():
    corpus = Corpus.load()
    assert corpus.contains_quote("D01", GARTNER_QUOTE)
    assert not corpus.contains_quote("D01", "85% of AI projects fail")
    assert corpus.get("d01") is corpus.get("D01")


def test_open_swarm_shows_false_corroboration():
    run = Run(ScriptedLLM(herd_script()))
    result = run.execute()
    assert not [e for e in run.tracer.events if e["type"] == "tool_result" and e["result"].startswith("ERROR")]
    assert result.grade == "wrong"
    assert result.score["false_consensus"]
    # Two supporting findings, one document underneath.
    assert result.score["supporting"] == 2
    assert result.score["supporting_roots"] == ["D08"]
    assert result.score["derived"] == 1


def test_quote_check_rejects_findings_that_cite_only_teammates():
    result = Run(ScriptedLLM(herd_script()), guards=Safeguards.parse("quote_check")).execute()
    assert result.score["supporting"] == 1
    assert result.score["derived"] == 0
    assert result.blocked == 1


def test_independence_hides_board_until_first_post():
    run = Run(ScriptedLLM(herd_script()), guards=Safeguards.parse("independence"))
    run.execute()
    assert run.blocked == 1


def test_read_budget_dial_limits_documents():
    script = {
        "lead": [call("spawn_researcher", question="q"), say("ok"), call("submit_verdict", verdict="PLAUSIBLE", confidence=50, origin_doc="D01", origin_type="forecast", summary="s")],
        "researcher-1": [call("read_document", doc_id="D01"), call("read_document", doc_id="D02"), say("done")],
    }
    run = Run(ScriptedLLM(script), dials=Dials(read_budget=1))
    run.execute()
    assert any(e["type"] == "limit" for e in run.tracer.events)


def test_correct_verdict_scores_correct():
    script = {
        "solo": [call("submit_verdict", verdict="BUSTED", confidence=80, origin_doc="D01", origin_type="forecast", summary="forecast")],
    }
    assert Run(ScriptedLLM(script), mode="single").execute().grade == "correct"


def test_budget_caps_researchers():
    script = {"lead": [call("spawn_researcher", question=f"q{i}") for i in range(8)] + [say("ok")]}
    run = Run(ScriptedLLM(script), guards=Safeguards.parse("budgets"))
    run.execute()
    assert run.researchers == 5


def test_origin_check_rejects_relays_and_unread_origins():
    script = {
        "solo": [
            call("submit_verdict", verdict="CONFIRMED", confidence=90, origin_doc="D08", origin_type="survey", summary="relay"),
            call("submit_verdict", verdict="BUSTED", confidence=80, origin_doc="D01", origin_type="forecast", summary="unread"),
            call("read_document", doc_id="D01"),
            call("submit_verdict", verdict="BUSTED", confidence=80, origin_doc="D01", origin_type="forecast", summary="read"),
        ],
    }
    run = Run(ScriptedLLM(script), mode="single", guards=Safeguards.parse("origin_check"))
    assert run.execute().grade == "correct"
    assert run.blocked == 2


def test_citation_index_shown_with_provenance():
    script = {"solo": [call("read_document", doc_id="D08"), say("done")]}
    run = Run(ScriptedLLM(script), mode="single", guards=Safeguards.parse("provenance"))
    run.execute()
    result = next(e for e in run.tracer.events if e["type"] == "tool_result")
    assert "CITATION INDEX" in result["result"] and "D01" in result["result"]
