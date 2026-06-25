# ai_services/insights/ai_insights.py
# ===================================================
# SkillPulse AI Engine — Role-Based Insights + RAG
# ===================================================

import os
import json
import logging
import inspect
from dotenv import load_dotenv

load_dotenv()
from openai import AsyncOpenAI
from json_repair import repair_json

logger = logging.getLogger(__name__)


# ===================================================
#  CLIENT
# ===================================================

def _get_client():
    mode = os.getenv("AI_MODE", "openrouter")
    if mode == "openrouter":
        return AsyncOpenAI(
            base_url=os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1"),
            api_key=os.getenv("OPENROUTER_API_KEY"),
        ), os.getenv("OPENROUTER_MODEL", "qwen/qwen3-14b")
    else:
        return AsyncOpenAI(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key="ollama",
        ), os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")


async def _call_llm(system_prompt: str, user_content: str) -> dict:
    client, model = _get_client()
    try:
        full_prompt = f"{system_prompt}\n\n=== REPOSITORY DATA TO ANALYZE ===\n{user_content}"
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": full_prompt}],
            temperature=0.4,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content
        try:
            return json.loads(repair_json(raw))
        except Exception as e:
            logger.error(f"Parse failed: {e}\nRaw: {raw[:300]}")
            raise ValueError(f"Unparseable response: {e}")
    finally:
        close_result = client.close()
        if inspect.isawaitable(close_result):
            await close_result


# ===================================================
#  HELPERS
# ===================================================

def _score_label(score: float) -> str:
    if score >= 85:   return "excellent"
    elif score >= 70: return "good"
    elif score >= 50: return "needs improvement"
    elif score >= 30: return "poor"
    else:             return "critically low"


def _test_label(test_files: int) -> str:
    if test_files == 0:
        return "0 test files (no automated tests exist)"
    elif test_files <= 2:
        return f"{test_files} test file(s) — minimal coverage"
    return f"{test_files} test files"


def _build_security_summary(security_report: dict) -> str:
    if not security_report or security_report.get("total_findings", 0) == 0:
        return "No security findings."
    total    = security_report.get("total_findings", 0)
    severity = security_report.get("severity_distribution", {})
    owasp    = security_report.get("owasp_distribution", {})
    files    = security_report.get("top_vulnerable_files", {})
    lines = [f"Total: {total} findings"]
    if severity:
        lines.append("Severity -> " + ", ".join(f"{k}: {v}" for k, v in sorted(severity.items())))
    if owasp:
        top = sorted(owasp.items(), key=lambda x: x[1], reverse=True)[:4]
        lines.append("OWASP -> " + ", ".join(f"{k} ({v})" for k, v in top))
    if files:
        lines.append("Top affected files -> " + ", ".join(list(files.keys())[:3]))
    return "\n".join(lines)


def _build_categorized_findings_summary(security_report: dict) -> str:
    categorized = security_report.get("categorized_findings") or {}
    if not categorized:
        return "HIGH: none\nMEDIUM: none\nLOW: none"

    lines: list[str] = []
    for severity in ("HIGH", "MEDIUM", "LOW"):
        per_file = categorized.get(severity, {}) or {}
        if not per_file:
            lines.append(f"{severity}: none")
            continue
        fragments = []
        for file_path, issues in list(per_file.items())[:5]:
            fragments.append(f"{file_path} ({len(issues)})")
        lines.append(f"{severity}: " + ", ".join(fragments))

    return "\n".join(lines)


# ===================================================
#  RAG CONTEXT BUILDER
# ===================================================

def _get_rag_context(doc_id, analysis_result: dict, security_report: dict) -> str:
    if not doc_id:
        return ""
    try:
        from ai_services.rag.rag_retriever import build_rag_context
        return build_rag_context(doc_id, analysis_result, security_report)
    except Exception as e:
        logger.warning(f"[RAG] Could not build RAG context: {e}")
        return ""


# ===================================================
#  PROMPTS
# ===================================================

_DEVELOPER_PROMPT = """You are SkillPulse AI — a senior software engineer giving code review feedback.

AUDIENCE: The developer who wrote this code.

TASK: Generate specific, honest, and actionable insights based on the metrics AND the CODING STANDARDS CONTEXT provided below.

HOW TO INTERPRET SCORES:
- code_quality -> driven by: style violations, duplication, function size, complexity
- maintainability -> driven by: docstring coverage, coupling, nesting depth, long functions
- architecture -> driven by: import coupling, inheritance depth, module separation
- problem_solving -> driven by: test files count, test function ratio, cyclomatic complexity, long functions
- security_score -> driven by: HIGH/MEDIUM/LOW security findings and affected files

CRITICAL RULES:
- You MUST use the CODING STANDARDS CONTEXT section to write your Fix points
- Every Fix must explicitly name the standard it comes from, for example:
  'per Clean Code: functions should do one thing'
  'per SOLID SRP: each module should have one responsibility'
  'per OWASP A08: validate all deserialized data'
  'per Google Python Style Guide: all public functions require docstrings'
- Why: cite the actual metric value
- Fix: cite the metric AND the specific standard/rule from the context
- Do NOT write generic advice. Every fix must reference a standard by name.
- Include final_categorized_findings grouped by HIGH, MEDIUM, LOW with file paths
- Use single quotes inside strings, never double quotes
- Return ONLY valid JSON

JSON structure:
{
  "skills_insights": {
    "code_quality": [
      "Why: reference the actual metric value that drives this score",
      "Fix: specific fix citing the standard name (e.g. per Clean Code: ...)"
    ],
    "maintainability": [
      "Why: reference the actual metric value",
      "Fix: specific fix citing the standard name"
    ],
    "architecture": [
      "Why: reference the actual metric value",
      "Fix: specific fix citing the standard name (e.g. per SOLID SRP: ...)"
    ],
    "problem_solving": [
      "Why: cite the actual drivers (test files count, complexity, etc.)",
      "Fix: specific fix citing the standard name (e.g. per TDD: ...)"
    ]
  },
  "security_insights": "Paragraph citing exact OWASP categories with counts, affected files, and the specific OWASP mitigation rule that applies from the context.",
  "final_categorized_findings": {
    "HIGH": ["file_path: concise issue summary"],
    "MEDIUM": ["file_path: concise issue summary"],
    "LOW": ["file_path: concise issue summary"]
  }
}"""

_MANAGER_PROMPT = """You are SkillPulse AI, acting as a Senior VP of Engineering and expert technical leader assessing an engineering team's code health.

AUDIENCE:
Engineering Managers, CTOs, and technical leaders who need strategic, plain-English insight into team velocity, maintainability, delivery risk, technical debt, and future execution cost.

TASK:
Turn the provided team metrics into prioritized management recommendations for the Team Dashboard. The output should help a manager decide where to allocate capacity, which risks need ownership, what quality gates to set, and what outcomes to monitor.

TONE AND STYLE:
- Professional, empathetic, strategic, and highly actionable.
- Write in natural, flowing sentences. Avoid robotic fragments like 'Metric: Score - Rating - Impact' or 'Poor architecture: 37.66 - poor - longer development cycles'.
- Sound like an experienced engineering leader giving concise next steps in a leadership review.
- Be direct about risks, but frame them constructively and with practical implications.
- Each recommendation should start with a manager-level action verb or action phrase.
- Do not prefix recommendations with labels like 'must', 'have to', 'should', 'better', 'mandatory', or 'nice to have'. The JSON bucket already carries the priority.
- Each string should be 1-2 polished sentences, not a label or bullet fragment.

MANAGER-ACTION RULES:
- Write for the person managing the team, not for the developer editing the code.
- Tell the manager what decision, prioritization, ownership, review cadence, or quality gate to put in place.
- Prefer manager verbs such as prioritize, assign an owner, allocate sprint capacity, set a release gate, schedule a refactor window, track, review, protect, standardize, and use.
- Avoid developer-task wording such as implement, refactor the code, add docstrings, decouple modules, write tests, clean up variables, or introduce a framework.
- Every recommendation should connect the metric to a management impact: delivery confidence, roadmap risk, coordination cost, onboarding, release readiness, or future capacity.

STRICT DATA RULES:
- Use ONLY the exact numbers and metrics provided in the payload. Do not invent, estimate, extrapolate, or perform unsupported math.
- You may interpret what a provided number implies, but you must not create new counts, percentages, trends, or scores.
- Every insight must be anchored to at least one provided metric, such as a skill score, total files analyzed, test file count, import coupling, complexity, docstring coverage, style violations, duplication, nesting depth, maintainability index, long functions, or unused variables.
- If the payload does not provide evidence for a claim, do not make that claim.

FOCUS AREAS:
- Discuss only Code Quality, Maintainability, Architecture, and Problem Solving.
- Do NOT mention or evaluate Security, Vulnerabilities, OWASP, compliance, exposure, or customer trust risk.
- Prefer meaning over raw numbers: explain how the metrics affect team velocity, release confidence, onboarding, regression risk, technical debt, maintenance cost, and ability to evolve the product.

PRIORITY MODEL:
- mandatory: immediate management actions that protect release confidence, delivery continuity, or future change safety. Use this for the most urgent measurable risks.
- highly_required: high-impact management actions that should be planned into the next sprint or near-term refactor window.
- nice_to_have: useful management follow-ups that are worth scheduling when delivery pressure allows, especially if they compound an existing strength.
- enhanced: polish or leverage actions that help a manager make a healthy area stronger, more repeatable, or easier to scale.

HOW TO INTERPRET COMMON SIGNALS:
- Strong problem-solving scores indicate the team can handle complex feature logic and ambiguous implementation work efficiently.
- Low or zero test files reduce release confidence and increase the chance that regressions reach users.
- High import coupling means changes are more likely to ripple across modules, increasing regression risk and slowing feature delivery.
- Low architecture scores suggest design boundaries may be weak, making future changes more expensive and coordination-heavy.
- Low maintainability, low docstring coverage, deep nesting, long functions, or high duplication point to growing technical debt and higher onboarding or handoff cost.
- Strong code quality, low style violations, and low duplication suggest the team has disciplined implementation habits that reduce review friction.

OUTPUT REQUIREMENTS:
- Return ONLY valid JSON. No markdown, no prose outside the JSON object.
- The JSON object must contain exactly one key: 'actionable_recommendations'.
- 'actionable_recommendations' must contain exactly these keys: 'mandatory', 'highly_required', 'nice_to_have', and 'enhanced'.
- Every recommendation list must contain strings. Empty lists are allowed when the metrics do not justify that priority because empty buckets are hidden in the UI.
- Generate only genuinely relevant items. Do not force exactly 3 items; fewer is better than filler.
- Each string must be a rich 1-3 sentence professional insight grounded in the actual metrics.
- Do not include generic advice like 'improve testing' unless it is tied to a concrete provided metric and a clear business impact.
- Do not copy wording, numbers, or examples from this prompt. Use only values from the repository data section.
- Use double quotes for valid JSON keys and strings.

JSON STRUCTURE:
{
  "actionable_recommendations": {
    "mandatory": [
      "A manager-level immediate action grounded in one or more provided risk metrics."
    ],
    "highly_required": [
      "A manager-level near-term high-impact action grounded in one or more provided metrics."
    ],
    "nice_to_have": [
      "A useful management follow-up grounded in one or more provided metrics."
    ],
    "enhanced": [
      "A manager-level polish or leverage action grounded in one or more provided strength metrics."
    ]
  }
}"""


_MANAGER_MEMBER_PROMPT = """You are SkillPulse AI, advising an Engineering Manager about one developer on their team.

AUDIENCE:
Engineering Manager, team lead, or CTO. The recommendations must help them coach, staff, pair, review, and support this developer.

TASK:
Generate concise manager-facing notes for this developer's detail panel. Explain what the manager should do with this person next, based only on the provided scores, timeline, and metrics.

MANAGER-ACTION RULES:
- Write to the manager, not to the developer.
- Prefer manager actions like assign, pair, use as reviewer, schedule coaching, protect focus time, set checkpoints, monitor, delegate, or create a growth plan.
- Avoid developer-facing instructions like 'write tests', 'refactor code', 'add docstrings', 'fix architecture', or 'clean up code'.
- Each item must be useful as a management decision or coaching action.
- Keep each item under 28 words.
- For low Problem Solving, recommend pair-programming, senior mentorship, scenario reviews, or complex-task coaching.
- For low Architecture, recommend design review ownership, architecture pairing, or scoped design checkpoints.
- For low Maintainability, recommend handoff review, documentation ownership, or refactor planning time.
- For low Code Quality, recommend review standards, checklist use, or targeted code review support.

DATA RULES:
- Use only the exact values provided in the payload.
- Do not invent trends, dates, scores, or causes.
- Discuss only Code Quality, Maintainability, Architecture, and Problem Solving.
- Do not mention Security, Vulnerabilities, OWASP, compliance, or customer trust risk.
- If there is no evidence for a key strength or improvement area, return an empty list for that key.
- If valid skill scores exist, do not return both lists empty.
- Use the provided skill_summary strongest and weakest fields to choose the most relevant manager action.

OUTPUT REQUIREMENTS:
- Return ONLY valid JSON.
- The JSON object must contain exactly these keys: 'key_strengths' and 'areas_for_improvement'.
- 'key_strengths' should describe how the manager can leverage this developer's strongest measurable capabilities.
- 'areas_for_improvement' should describe concrete manager actions to coach or support weaker areas.
- Return 1-2 key_strengths when there is a clear strongest score at or above 70.
- Return 1-2 areas_for_improvement when the weakest score is below 75 or materially lower than the strongest score.
- Do not force extra items; fewer is better than filler.

JSON STRUCTURE:
{
  "key_strengths": [
    "Use this developer as a reviewer for code-quality sensitive work because their code quality score is strong."
  ],
  "areas_for_improvement": [
    "Assign pair-programming sessions with a senior developer on complex algorithmic tasks because problem solving is the lowest score."
  ]
}"""


_RECRUITER_PROMPT = """You are SkillPulse AI — creating a candidate summary card for a recruiter.

AUDIENCE: HR professional. Zero technical background. Write like you are describing a person's work habits.

TASK: Summarize this developer's strengths and growth areas in plain, professional language.
Base it on the scores and profile facts — be specific and honest, not generic.

HOW TO TRANSLATE SCORES TO PLAIN LANGUAGE:
- High code quality = 'produces clean, organized work consistently'
- Good maintainability = 'writes code that teammates can easily understand and continue'
- Low problem_solving (from missing tests) = 'would benefit from training in quality assurance practices'
- Security issues = 'shows gaps in security awareness — addressable with structured training'
- Zero style violations = 'highly consistent and detail-oriented work style'

RULES:
- Exactly 3 highlights
- Highlight 1: lead with the developer's real strongest quality (back it with the score)
- Highlight 2: honest growth area — frame as a training opportunity, not a flaw
- Highlight 3: overall hiring potential and team collaboration fit
- Max 25 words per highlight
- ZERO technical terms (no 'cyclomatic', 'OWASP', 'coupling', 'pytest', 'docstring', etc.)
- Use single quotes inside strings, never double quotes
- Return ONLY valid JSON

JSON structure:
{
  "key_highlights": [
    "Highlight 1 — specific strength backed by performance level",
    "Highlight 2 — growth area as a training opportunity",
    "Highlight 3 — hiring potential and team fit"
  ]
}"""


# ===================================================
#  CONTENT BUILDERS
# ===================================================

def _developer_content(analysis: dict, security_report: dict, rag_context: str = "") -> str:
    scores = analysis.get("scores", {})
    m      = analysis.get("aggregate_metrics", {})

    base = f"""SCORES (out of 100):
- Code Quality:    {scores.get('code_quality')} — {_score_label(scores.get('code_quality', 0))}
- Maintainability: {scores.get('maintainability')} — {_score_label(scores.get('maintainability', 0))}
- Architecture:    {scores.get('architecture')} — {_score_label(scores.get('architecture', 0))}
- Security Score:  {scores.get('security_score')} — {_score_label(scores.get('security_score', 0))}
- Problem Solving: {scores.get('problem_solving')} — {_score_label(scores.get('problem_solving', 0))}

METRICS (use these to explain each score):
- Total files: {m.get('total_files')} | Test files: {_test_label(m.get('test_files', 0))}
- Avg test function ratio: {m.get('avg_test_function_ratio', 0)}
- Avg cyclomatic complexity: {m.get('avg_cyclomatic_complexity')} (healthy < 5, warning > 10)
- Avg function size: {m.get('avg_function_size', 0):.1f} lines (healthy < 20)
- Long functions: {m.get('long_functions', 0)}
- Deep nesting instances: {m.get('deep_nesting', 0)} | Avg nesting depth: {m.get('avg_nesting_depth', 0):.2f}
- Docstring coverage: {m.get('avg_docstring_coverage', 0)*100:.0f}% (ideal > 80%)
- Code duplication: {m.get('avg_duplication_score', 0)*100:.0f}% (ideal < 15%)
- Import coupling total: {m.get('import_coupling_total')} (high = tightly coupled modules)
- Style violations: {m.get('style_violations', 0)}
- Unused variables: {m.get('unused_variables', 0)}

SECURITY DATA:
{_build_security_summary(security_report)}

SECURITY FINDINGS GROUPED BY SEVERITY AND FILE:
{_build_categorized_findings_summary(security_report)}"""

    if rag_context:
        base += f"\n\nCODING STANDARDS CONTEXT (you MUST cite these standards in your Fix points):\n{rag_context}"

    return base


def _manager_content(analysis: dict, security_report: dict, rag_context: str = "") -> str:
    scores = analysis.get("scores", {})
    m      = analysis.get("aggregate_metrics", {})

    base = f"""EXACT SCORES (out of 100, use these exact values only):
- Code Quality: {scores.get('code_quality')}
- Maintainability: {scores.get('maintainability')}
- Architecture: {scores.get('architecture')}
- Problem Solving: {scores.get('problem_solving')}
- Overall: {scores.get('overall')}

EXACT TEAM METRICS (use these exact values only):
- Team size: {m.get('team_size')}
- Repository count: {m.get('repository_count')}
- Total files analyzed: {m.get('total_files_analyzed')}
- Test files: {m.get('test_files', 0)}
- Avg test function ratio: {m.get('avg_test_function_ratio', 0)}
- Avg complexity: {m.get('avg_cyclomatic_complexity')} | Long functions: {m.get('long_functions', 0)}
- Avg function size: {m.get('avg_function_size', 0)}
- Avg nesting depth: {m.get('avg_nesting_depth', 0)}
- Avg maintainability index: {m.get('avg_maintainability_index', 0)}
- Docstring coverage value: {m.get('avg_docstring_coverage', 0)}
- Import coupling: {m.get('import_coupling_total')}
- Style violations: {m.get('style_violations', 0)}
- Code duplication value: {m.get('avg_duplication_score', 0)}
- Unused variables: {m.get('unused_variables', 0)}
- Total lines of code: {m.get('total_loc', 0)}"""

    if rag_context:
        base += f"\n\nCODING STANDARDS CONTEXT:\n{rag_context}"

    return base


def _manager_member_content(analysis: dict, security_report: dict, rag_context: str = "") -> str:
    developer = analysis.get("developer", {})
    scores = analysis.get("scores", {})
    m = analysis.get("aggregate_metrics", {})
    skill_summary = analysis.get("skill_summary", {})
    timeline = analysis.get("timeline", [])

    base = f"""DEVELOPER PROFILE:
- Name: {developer.get('name')}
- Specialization: {developer.get('specialization')}
- Analysis count: {developer.get('analysis_count')}
- Repository count: {developer.get('repository_count')}
- Overall delta: {developer.get('overall_delta')}

EXACT SCORES (out of 100, use these exact values only):
- Code Quality: {scores.get('code_quality')}
- Maintainability: {scores.get('maintainability')}
- Architecture: {scores.get('architecture')}
- Problem Solving: {scores.get('problem_solving')}
- Overall: {scores.get('overall')}

SKILL SUMMARY:
{json.dumps(skill_summary, ensure_ascii=False)}

EXACT CONTRIBUTION METRICS (use these exact values only):
- Total files analyzed: {m.get('total_files_analyzed')}
- Test files: {m.get('test_files', 0)}
- Avg test function ratio: {m.get('avg_test_function_ratio', 0)}
- Avg complexity: {m.get('avg_cyclomatic_complexity')} | Long functions: {m.get('long_functions', 0)}
- Avg function size: {m.get('avg_function_size', 0)}
- Avg nesting depth: {m.get('avg_nesting_depth', 0)}
- Avg maintainability index: {m.get('avg_maintainability_index', 0)}
- Docstring coverage value: {m.get('avg_docstring_coverage', 0)}
- Import coupling: {m.get('import_coupling_total')}
- Style violations: {m.get('style_violations', 0)}
- Code duplication value: {m.get('avg_duplication_score', 0)}
- Unused variables: {m.get('unused_variables', 0)}
- Total lines of code: {m.get('total_loc', 0)}

RECENT PERFORMANCE TIMELINE POINTS:
{json.dumps(timeline, ensure_ascii=False)}"""

    if rag_context:
        base += f"\n\nCODING STANDARDS CONTEXT:\n{rag_context}"

    return base


def _recruiter_content(analysis: dict, security_report: dict, rag_context: str = "") -> str:
    scores    = analysis.get("scores", {})
    m         = analysis.get("aggregate_metrics", {})
    total_sec = security_report.get("total_findings", 0) if security_report else 0

    return f"""PERFORMANCE SCORES (out of 100):
- Code Quality (cleanliness and consistency): {scores.get('code_quality')} — {_score_label(scores.get('code_quality', 0))}
- Maintainability (ease of collaboration):    {scores.get('maintainability')} — {_score_label(scores.get('maintainability', 0))}
- Architecture (project organization):        {scores.get('architecture')} — {_score_label(scores.get('architecture', 0))}
- Security Score (safe coding awareness):     {scores.get('security_score')} — {_score_label(scores.get('security_score', 0))}
- Problem Solving (testing and logic):        {scores.get('problem_solving')} — {_score_label(scores.get('problem_solving', 0))}
- Overall Score:                              {scores.get('overall')} — {_score_label(scores.get('overall', 0))}

PROFILE FACTS:
- Documentation: {m.get('avg_docstring_coverage', 0)*100:.0f}% of code is documented
- Automated testing: {_test_label(m.get('test_files', 0))}
- Style consistency: {'perfect — zero violations across all files' if m.get('style_violations', 0) == 0 else f"{m.get('style_violations')} inconsistencies found"}
- Security issues found: {total_sec} ({'none' if total_sec == 0 else 'minor — trainable' if total_sec <= 5 else 'moderate' if total_sec <= 15 else 'significant — needs attention'})"""


# ===================================================
#  ROLE ROUTER
# ===================================================

_ROLE_MAP = {
    "developer": (_DEVELOPER_PROMPT, _developer_content),
    "manager":   (_MANAGER_PROMPT,   _manager_content),
    "manager_member": (_MANAGER_MEMBER_PROMPT, _manager_member_content),
    "recruiter": (_RECRUITER_PROMPT, _recruiter_content),
}


async def generate_insights(
    role: str,
    analysis_result: dict,
    security_report: dict = None,
    doc_id: str = None,
) -> dict:
    security_report = security_report or {}
    role = role.lower()
    print(f"[RAG DEBUG] doc_id received = {doc_id}")
    print(f"[RAG DEBUG] role = {role}")

    if role not in _ROLE_MAP:
        logger.warning(f"Unknown role '{role}' — defaulting to developer")
        role = "developer"

    prompt, content_fn = _ROLE_MAP[role]

    rag_context = _get_rag_context(doc_id, analysis_result, security_report)
    print(f"[RAG DEBUG] rag_context length = {len(rag_context)}")

    if rag_context:
        logger.info(f"[RAG] Context injected into prompt ({len(rag_context)} chars)")
    else:
        logger.info("[RAG] No context available — running without RAG")

    logger.info(f"Generating insights | role={role} | mode={os.getenv('AI_MODE')}")

    result = await _call_llm(prompt, content_fn(analysis_result, security_report, rag_context))
    logger.info("Insights generated.")
    return result
