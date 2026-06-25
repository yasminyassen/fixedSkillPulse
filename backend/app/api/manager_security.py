from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth_utils import require_role
from app.db.database import get_db
from app.db.models import AnalysisRun, Repository, SecurityFinding, SkillScore, User, UserRole
from app.schemas.manager_security_schemas import (
    CommonSecurityIssue,
    ContributorIssueGroup,
    ContributorSecurityImpact,
    DetectedVulnerability,
    ManagerSecurityRepo,
    RepositorySecurityDetail,
    RepositorySecuritySummary,
    SecurityMemberScore,
    SecurityRiskBreakdown,
    SecurityTrendPoint,
    TeamSecurityOverview,
)
from app.services.security_service import normalize_severity


router = APIRouter(prefix="/manager/security", tags=["manager-security"])

SEVERITY_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _run_time(run: AnalysisRun) -> datetime:
    value = run.completed_at or run.triggered_at or datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _round_score(value: float) -> float:
    return round(float(value or 0.0), 2)


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _latest_manager_runs_by_repo(db: Session, manager_id: int) -> list[AnalysisRun]:
    runs = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.user_id == manager_id,
            AnalysisRun.analysis_scope == "team_contributions",
            AnalysisRun.status == "completed",
        )
        .order_by(AnalysisRun.completed_at.desc(), AnalysisRun.triggered_at.desc())
        .all()
    )
    latest: dict[int, AnalysisRun] = {}
    for run in runs:
        if run.repository_id not in latest:
            latest[run.repository_id] = run
    return list(latest.values())


def _latest_manager_run_for_repo(db: Session, manager_id: int, repo_id: int) -> AnalysisRun | None:
    return (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.user_id == manager_id,
            AnalysisRun.repository_id == repo_id,
            AnalysisRun.analysis_scope == "team_contributions",
            AnalysisRun.status == "completed",
        )
        .order_by(AnalysisRun.completed_at.desc(), AnalysisRun.triggered_at.desc())
        .first()
    )


def _previous_manager_run_for_repo(
    db: Session,
    manager_id: int,
    repo_id: int,
    current_run_id: int,
) -> AnalysisRun | None:
    return (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.user_id == manager_id,
            AnalysisRun.repository_id == repo_id,
            AnalysisRun.id != current_run_id,
            AnalysisRun.analysis_scope == "team_contributions",
            AnalysisRun.status == "completed",
        )
        .order_by(AnalysisRun.completed_at.desc(), AnalysisRun.triggered_at.desc())
        .first()
    )


def _findings_for_runs(db: Session, run_ids: list[int]) -> list[SecurityFinding]:
    if not run_ids:
        return []
    return (
        db.query(SecurityFinding)
        .filter(SecurityFinding.analysis_run_id.in_(run_ids))
        .all()
    )


def _dedupe_findings(findings: list[SecurityFinding]) -> list[SecurityFinding]:
    seen: set[tuple] = set()
    result: list[SecurityFinding] = []
    for finding in findings:
        key = (
            finding.analysis_run_id,
            (finding.file_path or "").replace("\\", "/").strip().lower(),
            (finding.rule or "").strip().lower(),
            finding.line_number or 0,
            (finding.cwe or "").strip().upper(),
            normalize_severity(finding.severity),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result


def _finding_fingerprint(finding: SecurityFinding) -> tuple:
    return (
        (finding.file_path or "").replace("\\", "/").strip().lower(),
        finding.line_number or 0,
        (finding.rule or "").strip().lower(),
        (finding.cwe or "").strip().upper(),
        (finding.owasp_category or "").strip().lower(),
    )


def _user_issue_delta(
    current_findings: list[SecurityFinding],
    previous_findings: list[SecurityFinding],
) -> dict[int, dict[str, int]]:
    if not previous_findings:
        return {}

    current_by_user: dict[int, set[tuple]] = defaultdict(set)
    previous_by_user: dict[int, set[tuple]] = defaultdict(set)

    for finding in _dedupe_findings(current_findings):
        if finding.user_id is not None:
            current_by_user[finding.user_id].add(_finding_fingerprint(finding))

    for finding in _dedupe_findings(previous_findings):
        if finding.user_id is not None:
            previous_by_user[finding.user_id].add(_finding_fingerprint(finding))

    result: dict[int, dict[str, int]] = {}
    for user_id in set(current_by_user) | set(previous_by_user):
        current = current_by_user.get(user_id, set())
        previous = previous_by_user.get(user_id, set())
        result[user_id] = {
            "introduced": len(current - previous),
            "fixed": len(previous - current),
        }
    return result


def _risk_breakdown(findings: list[SecurityFinding]) -> SecurityRiskBreakdown:
    counts = Counter(normalize_severity(finding.severity) for finding in findings)
    high = counts.get("HIGH", 0)
    medium = counts.get("MEDIUM", 0)
    low = counts.get("LOW", 0)
    return SecurityRiskBreakdown(high=high, medium=medium, low=low, total=high + medium + low)


def _security_score_for_runs(db: Session, run_ids: list[int]) -> float:
    if not run_ids:
        return 0.0
    rows = (
        db.query(SkillScore.security_awareness_score)
        .join(User, SkillScore.user_id == User.id)
        .filter(
            SkillScore.analysis_run_id.in_(run_ids),
            User.role == UserRole.developer,
        )
        .all()
    )
    return _round_score(_avg([float(row[0] or 0.0) for row in rows]))


def _issue_title(finding: SecurityFinding) -> str:
    text = " ".join(
        str(part or "")
        for part in (finding.rule, finding.description, finding.cwe, finding.owasp_category)
    ).lower()
    if any(token in text for token in ("secret", "password", "token", "credential", "api key")):
        return "Insecure secret management"
    if any(token in text for token in ("sql", "injection", "xss", "validation", "sanitize", "cwe-79", "cwe-89")):
        return "Input validation weaknesses"
    if any(token in text for token in ("auth", "session", "jwt", "access control", "permission", "cwe-287", "cwe-306", "cwe-862", "cwe-863")):
        return "Weak authentication patterns"
    if any(token in text for token in ("dependency", "package", "requirements", "safety", "vulnerable")):
        return "Vulnerable dependencies"
    if any(token in text for token in ("config", "debug", "cors", "misconfiguration")):
        return "Security misconfiguration"
    return finding.rule or finding.owasp_category or finding.cwe or "Unclassified security issue"


def _common_issues(findings: list[SecurityFinding], run_repo_ids: dict[int, int]) -> list[CommonSecurityIssue]:
    grouped: dict[str, dict] = {}
    for finding in findings:
        title = _issue_title(finding)
        entry = grouped.setdefault(
            title,
            {"count": 0, "repos": set(), "severity": "LOW"},
        )
        entry["count"] += 1
        repo_id = run_repo_ids.get(finding.analysis_run_id)
        if repo_id is not None:
            entry["repos"].add(repo_id)
        severity = normalize_severity(finding.severity)
        if SEVERITY_ORDER[severity] > SEVERITY_ORDER[entry["severity"]]:
            entry["severity"] = severity

    return [
        CommonSecurityIssue(
            title=title,
            severity=data["severity"].title(),
            occurrences=data["count"],
            repositories_affected=len(data["repos"]),
        )
        for title, data in sorted(grouped.items(), key=lambda item: item[1]["count"], reverse=True)[:5]
    ]


def _trend(db: Session, manager_id: int) -> list[SecurityTrendPoint]:
    runs = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.user_id == manager_id,
            AnalysisRun.analysis_scope == "team_contributions",
            AnalysisRun.status == "completed",
        )
        .order_by(AnalysisRun.completed_at.asc(), AnalysisRun.triggered_at.asc())
        .all()
    )
    run_ids = [run.id for run in runs]
    run_by_id = {run.id: run for run in runs}
    grouped: dict[str, Counter] = defaultdict(Counter)
    for finding in _dedupe_findings(_findings_for_runs(db, run_ids)):
        run = run_by_id.get(finding.analysis_run_id)
        if not run:
            continue
        when = _run_time(run)
        period = when.strftime("%Y-%m")
        grouped[period][normalize_severity(finding.severity)] += 1

    return [
        SecurityTrendPoint(
            period=period,
            label=datetime.strptime(period, "%Y-%m").strftime("%b"),
            high=counts.get("HIGH", 0),
            medium=counts.get("MEDIUM", 0),
            low=counts.get("LOW", 0),
        )
        for period, counts in sorted(grouped.items())[-3:]
    ]


def _systemic_analysis(common: list[CommonSecurityIssue], repo_count: int) -> str:
    if not common:
        return "No recurring security pattern is visible in the latest manager-run repository analyses."
    top = common[0]
    if top.repositories_affected > 1:
        return (
            f"{top.title} appears {top.occurrences} times across {top.repositories_affected} repositories, "
            "which points to a process-level pattern rather than an isolated implementation mistake."
        )
    return (
        f"The most common current issue is {top.title.lower()} with {top.occurrences} occurrence(s). "
        f"Across {repo_count} repository analysis snapshot(s), this is best treated as a targeted remediation item."
    )


def _why_this_matters() -> list[str]:
    return [
        "Early detection reduces the chance that preventable vulnerabilities reach production.",
        "Shared security patterns help managers prioritize coaching and review standards across the team.",
        "Continuous security monitoring keeps release decisions tied to current repository evidence.",
    ]


def _member_scores(db: Session, run_ids: list[int]) -> list[SecurityMemberScore]:
    if not run_ids:
        return []
    rows = (
        db.query(SkillScore, AnalysisRun, User)
        .join(AnalysisRun, SkillScore.analysis_run_id == AnalysisRun.id)
        .join(User, SkillScore.user_id == User.id)
        .filter(SkillScore.analysis_run_id.in_(run_ids), User.role == UserRole.developer)
        .all()
    )
    findings = _findings_for_runs(db, run_ids)
    findings_by_user: dict[int, list[SecurityFinding]] = defaultdict(list)
    for finding in findings:
        if finding.user_id is not None:
            findings_by_user[finding.user_id].append(finding)

    grouped: dict[int, dict] = {}
    for score, run, user in rows:
        entry = grouped.setdefault(user.id, {"user": user, "scores": [], "repos": set()})
        entry["scores"].append(float(score.security_awareness_score or 0.0))
        entry["repos"].add(run.repository_id)

    result: list[SecurityMemberScore] = []
    for user_id, data in grouped.items():
        breakdown = _risk_breakdown(_dedupe_findings(findings_by_user.get(user_id, [])))
        user = data["user"]
        result.append(
            SecurityMemberScore(
                id=user.id,
                full_name=user.full_name,
                username=user.username,
                avatar_url=user.avatar_url,
                specialization=user.specialization.value if user.specialization else None,
                repository_count=len(data["repos"]),
                security_score=_round_score(_avg(data["scores"])),
                high=breakdown.high,
                medium=breakdown.medium,
                low=breakdown.low,
            )
        )
    return sorted(result, key=lambda item: item.security_score)


def _vulnerability_item(finding: SecurityFinding, users_by_id: dict[int, User]) -> DetectedVulnerability:
    contributor = users_by_id.get(finding.user_id) if finding.user_id is not None else None
    return DetectedVulnerability(
        id=finding.id,
        title=_issue_title(finding),
        severity=normalize_severity(finding.severity).title(),
        description=finding.description,
        file_path=finding.file_path,
        line_number=finding.line_number,
        cwe=finding.cwe,
        owasp_category=finding.owasp_category,
        contributor_id=contributor.id if contributor else None,
        contributor_name=contributor.full_name if contributor else None,
    )


def _release_readiness(repo_name: str | None, breakdown: SecurityRiskBreakdown) -> str:
    label = repo_name or "This repository"
    if breakdown.high:
        return (
            f"{label} is not release-ready while {breakdown.high} high-risk finding(s) remain open. "
            "Treat these as blocking issues before production deployment."
        )
    if breakdown.medium:
        return (
            f"{label} can move toward release after targeted review of {breakdown.medium} medium-risk finding(s). "
            "The current risk is manageable only with documented remediation ownership."
        )
    if breakdown.low:
        return (
            f"{label} has no high or medium-risk findings in the latest analysis. "
            f"The remaining {breakdown.low} low-risk item(s) can be handled as release polish."
        )
    return f"{label} has no detected security findings in the latest manager-run analysis."


def _recommended_actions(breakdown: SecurityRiskBreakdown, common: list[CommonSecurityIssue]) -> list[str]:
    actions: list[str] = []
    if breakdown.high:
        actions.append(f"Block production release until {breakdown.high} high-risk finding(s) are remediated or explicitly accepted.")
    if breakdown.medium:
        actions.append(f"Assign owners for {breakdown.medium} medium-risk finding(s) and verify fixes before the next release candidate.")
    if common:
        actions.append(f"Run a focused review for {common[0].title.lower()} because it is the dominant security pattern in this view.")
    if not actions:
        actions.append("Keep the repository on regular security analysis cadence and monitor for newly introduced findings.")
    return actions


def _contributor_impacts(
    db: Session,
    run_id: int,
    findings: list[SecurityFinding],
    previous_findings: list[SecurityFinding],
) -> list[ContributorSecurityImpact]:
    rows = (
        db.query(SkillScore, User)
        .join(User, SkillScore.user_id == User.id)
        .filter(SkillScore.analysis_run_id == run_id, User.role == UserRole.developer)
        .all()
    )
    findings_by_user: dict[int, list[SecurityFinding]] = defaultdict(list)
    for finding in findings:
        if finding.user_id is not None:
            findings_by_user[finding.user_id].append(finding)

    deltas = _user_issue_delta(findings, previous_findings)
    result: list[ContributorSecurityImpact] = []
    for score, user in rows:
        breakdown = _risk_breakdown(_dedupe_findings(findings_by_user.get(user.id, [])))
        delta = deltas.get(user.id, {})
        issue_count = breakdown.total
        score_value = _round_score(score.security_awareness_score or 0.0)
        introduced = int(delta.get("introduced", 0))
        fixed = int(delta.get("fixed", 0))
        if breakdown.high or introduced > fixed:
            net_impact = "Risky"
        elif fixed > introduced or issue_count == 0 or score_value >= 85:
            net_impact = "Positive"
        else:
            net_impact = "Neutral"
        result.append(
            ContributorSecurityImpact(
                id=user.id,
                full_name=user.full_name,
                username=user.username,
                avatar_url=user.avatar_url,
                specialization=user.specialization.value if user.specialization else None,
                security_score=score_value,
                issue_count=issue_count,
                issues_fixed=fixed,
                issues_introduced=introduced,
                high=breakdown.high,
                medium=breakdown.medium,
                low=breakdown.low,
                net_impact=net_impact,
            )
        )
    return sorted(
        result,
        key=lambda item: (item.high, item.issues_introduced, item.issue_count),
        reverse=True,
    )


@router.get("/repos", response_model=list[ManagerSecurityRepo])
def get_manager_security_repos(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["manager"])),
):
    latest_runs = _latest_manager_runs_by_repo(db, current_user.id)
    result: list[ManagerSecurityRepo] = []
    for run in sorted(latest_runs, key=_run_time, reverse=True):
        findings = _dedupe_findings(_findings_for_runs(db, [run.id]))
        result.append(
            ManagerSecurityRepo(
                id=run.repository.id,
                name=run.repository.name,
                full_name=run.repository.full_name,
                is_private=bool(run.repository.is_private),
                last_analyzed_at=run.completed_at,
                security_score=_security_score_for_runs(db, [run.id]),
                total_issues=len(findings),
            )
        )
    return result


@router.get("/team", response_model=TeamSecurityOverview)
def get_team_security_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["manager"])),
):
    latest_runs = _latest_manager_runs_by_repo(db, current_user.id)
    run_ids = [run.id for run in latest_runs]
    run_repo_ids = {run.id: run.repository_id for run in latest_runs}
    findings = _dedupe_findings(_findings_for_runs(db, run_ids))
    breakdown = _risk_breakdown(findings)
    common = _common_issues(findings, run_repo_ids)
    members = _member_scores(db, run_ids)

    return TeamSecurityOverview(
        overall_score=_security_score_for_runs(db, run_ids),
        repository_count=len(latest_runs),
        total_issues=breakdown.total,
        team_members=len(members),
        risk_breakdown=breakdown,
        trend=_trend(db, current_user.id),
        common_issues=common,
        systemic_risk_analysis=_systemic_analysis(common, len(latest_runs)),
        why_this_matters=_why_this_matters(),
        members=members,
    )


@router.get("/repositories/{repo_id}", response_model=RepositorySecurityDetail)
def get_repository_security_detail(
    repo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["manager"])),
):
    run = _latest_manager_run_for_repo(db, current_user.id, repo_id)
    if not run:
        raise HTTPException(status_code=404, detail="Repository security analysis not found")

    findings = _dedupe_findings(_findings_for_runs(db, [run.id]))
    previous_run = _previous_manager_run_for_repo(db, current_user.id, repo_id, run.id)
    previous_findings = _dedupe_findings(_findings_for_runs(db, [previous_run.id])) if previous_run else []
    breakdown = _risk_breakdown(findings)
    score = _security_score_for_runs(db, [run.id])
    users_by_id = {
        user.id: user
        for user in (
            db.query(User)
            .join(SkillScore, SkillScore.user_id == User.id)
            .filter(SkillScore.analysis_run_id == run.id)
            .all()
        )
    }
    vulnerabilities = sorted(
        [_vulnerability_item(finding, users_by_id) for finding in findings],
        key=lambda item: SEVERITY_ORDER.get(item.severity.upper(), 0),
        reverse=True,
    )
    grouped_by_severity: list[ContributorIssueGroup] = []
    for severity in ("High", "Medium", "Low"):
        issues = [item for item in vulnerabilities if item.severity == severity]
        if issues:
            grouped_by_severity.append(ContributorIssueGroup(severity=severity, issues=issues))

    common = _common_issues(findings, {run.id: run.repository_id})

    return RepositorySecurityDetail(
        repository=RepositorySecuritySummary(
            id=run.repository.id,
            name=run.repository.name,
            full_name=run.repository.full_name,
            security_score=score,
            total_issues=breakdown.total,
            high=breakdown.high,
            medium=breakdown.medium,
            low=breakdown.low,
        ),
        release_readiness=_release_readiness(run.repository.name, breakdown),
        detected_vulnerabilities=vulnerabilities[:10],
        recommended_actions=_recommended_actions(breakdown, common),
        contributor_impacts=_contributor_impacts(db, run.id, findings, previous_findings),
        issues_by_contributor=grouped_by_severity,
    )
