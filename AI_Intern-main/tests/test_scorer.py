import os
from pathlib import Path
from dotenv import load_dotenv
import pytest

# The scorer relies on a previously generated AI Deep Research Report.
# We therefore reuse the existing `run_deep_research` helper to make sure
# the Markdown report is present before invoking the scoring pipeline.
from src.research import run_deep_research
from src.scorer import run_project_scoring

load_dotenv()

PAGE_ID = "1eb7cf9e-26b8-81a3-b3ff-ca70731a64dd"  # Blockmesh Project Page ID


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("NOTION_TOKEN")
    or not os.getenv("OPENAI_API_KEY")
    or not PAGE_ID,
    reason="Real credentials are required to run integration test.",
)
def test_run_project_scoring_real_world(tmp_path: Path):
    """End-to-end integration test: deep-research ➜ scorer.

    The test ensures that:
    1. A deep-research report can be generated for the fixed *PAGE_ID*.
    2. The scoring helper produces a JSON file under /reports and the file is non-empty.
    """

    # ------------------------------------------------------------------
    # 1. Generate (or regenerate) the AI Deep Research Report so that the
    #    scorer has the necessary context.
    # ------------------------------------------------------------------
    ddq_md_path = tmp_path / "ddq.md"
    report_path = run_deep_research(PAGE_ID, ddq_md_path)
    assert report_path.exists(), "Deep Research report was not created as expected."

    # ------------------------------------------------------------------
    # 2. Execute the scoring pipeline
    # ------------------------------------------------------------------
    json_path = run_project_scoring(PAGE_ID)

    # ------------------------------------------------------------------
    # 3. Assertions – JSON exists and is non-trivial
    # ------------------------------------------------------------------
    assert json_path.exists(), "Score JSON file was not created."
    # A minimal sanity check on file size (>1KB) ensures non-empty content.
    assert json_path.stat().st_size > 1024, "Score JSON file appears unexpectedly small."

    # Optional: basic JSON structure validation (key presence).
    import json as _json
    data = _json.loads(json_path.read_text(encoding="utf-8"))
    required_keys = {"IDO", "Advisory", "Investment", "LiquidProgram", "BullCase", "BearCase"}
    missing = required_keys - data.keys()
    assert not missing, f"Missing expected keys in score JSON: {missing}"

    # ------------------------------------------------------------------
    # DEBUG: Inspect the textual context passed into run_project_scoring
    # ------------------------------------------------------------------
    # NOTE: Comment-out or delete the following block once you have
    # verified that the correct context is being fetched for the scorer.
    # from src.research import _fetch_ddq_markdown, _fetch_calls_text, _fetch_freeform_text
    # from pathlib import Path as _Path

    # ddq_text_dbg = _fetch_ddq_markdown(PAGE_ID)
    # calls_text_dbg = _fetch_calls_text(PAGE_ID)
    # freeform_text_dbg = _fetch_freeform_text(PAGE_ID)
    # report_md_path_dbg = _Path("reports") / f"report_{PAGE_ID}.md"
    # ai_text_dbg = (
    #     report_md_path_dbg.read_text(encoding="utf-8")
    #     if report_md_path_dbg.exists()
    #     else "<AI Deep Research Report not found>"
    # )

    # print("\n[DEBUG] Context excerpts passed to scorer (first 500 characters each):")
    # print("\n--- DDQ_TEXT ---\n", ddq_text_dbg[:500])
    # print("\n--- CALLS_TEXT ---\n", calls_text_dbg[:500])
    # print("\n--- FREEFORM_TEXT ---\n", freeform_text_dbg[:500])
    # print("\n--- AI_TEXT ---\n", ai_text_dbg[:500], "\n")
    # ------------------------------------------------------------------
