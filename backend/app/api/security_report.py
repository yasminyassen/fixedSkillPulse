from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.db.models import AnalysisRun, SecurityFinding, SkillScore
from app.core.auth_utils import get_current_user
from app.db.models import User
from fastapi import Request
from app.core.rate_limiter import limiter
from app.services.security_service import compute_security_score_breakdown


router = APIRouter(prefix="/security-report", tags=["security"])


def _severity_bucket(severity: str | None) -> str:
    s = (severity or "MEDIUM").upper()
    if s == "CRITICAL":
        return "HIGH"
    if s in {"HIGH", "MEDIUM", "LOW"}:
        return s
    return "MEDIUM"


@router.get("/{analysis_id}")
@limiter.limit("20/minute")
def get_security_report(
    request: Request,
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    has_access = (
        db.query(SkillScore)
        .join(AnalysisRun, SkillScore.analysis_run_id == AnalysisRun.id)
        .filter(
            SkillScore.analysis_run_id == analysis_id,
            SkillScore.user_id == current_user.id,
            AnalysisRun.user_id == current_user.id,
        )
        .first()
    )
    if not has_access:
        raise HTTPException(status_code=404, detail="Analysis report not found")

    run = db.query(AnalysisRun).filter(AnalysisRun.id == analysis_id).first()
    failed_tools = []
    if isinstance(run.ai_insights, dict):
        security_report = run.ai_insights.get("security_report", {})
        failed_tools = (
            run.ai_insights.get("failed_tools")
            or security_report.get("failed_tools")
            or []
        )

    findings = db.query(SecurityFinding).filter(
        SecurityFinding.analysis_run_id == analysis_id
    ).all()
    security_score_inputs = [
        {
            "severity": f.severity,
            "cwe": f.cwe,
            "file_path": f.file_path,
            "tool": f.tool,
        }
        for f in findings
    ]
    security_score_breakdown = compute_security_score_breakdown(security_score_inputs)

    if not findings:
        return {
            "analysis_id": analysis_id,
            "total_findings": 0,
            "severity_distribution": {},
            "tool_distribution": {},
            "owasp_distribution": {},
            "categorized_findings": {
                "HIGH": {},
                "MEDIUM": {},
                "LOW": {},
            },
            "failed_tools": failed_tools,
            "security_score_breakdown": security_score_breakdown,
        }

    total = len(findings)

    severity_stats = (
        db.query(SecurityFinding.severity, func.count())
        .filter(SecurityFinding.analysis_run_id == analysis_id)
        .group_by(SecurityFinding.severity)
        .all()
    )

    tool_stats = (
        db.query(SecurityFinding.tool, func.count())
        .filter(SecurityFinding.analysis_run_id == analysis_id)
        .group_by(SecurityFinding.tool)
        .all()
    )

    owasp_stats = (
        db.query(SecurityFinding.owasp_category, func.count())
        .filter(SecurityFinding.analysis_run_id == analysis_id)
        .group_by(SecurityFinding.owasp_category)
        .all()
    )
    
    file_stats = (
    db.query(SecurityFinding.file_path, func.count())
    .filter(SecurityFinding.analysis_run_id == analysis_id)
    .group_by(SecurityFinding.file_path)
    .order_by(func.count().desc())
    .limit(5)
    .all()
    )

    categorized_findings = {
        "HIGH": {},
        "MEDIUM": {},
        "LOW": {},
    }

    for f in findings:
        severity = _severity_bucket(f.severity)
        file_path = f.file_path or "unknown"
        categorized_findings[severity].setdefault(file_path, []).append(
            {
                "tool": f.tool,
                "rule": f.rule,
                "owasp_category": f.owasp_category or "Unknown",
                "line_number": f.line_number or 0,
                "description": f.description,
            }
        )

    return {

        "analysis_id": analysis_id,

        "total_findings": total,

        "severity_distribution": {
            k: v for k, v in severity_stats
        },

        "tool_distribution": {
            k: v for k, v in tool_stats
        },

        "owasp_distribution": {
            (k or "Unknown"): v for k, v in owasp_stats
        },
        
        "top_vulnerable_files": {
            k: v for k, v in file_stats
        },
        "categorized_findings": categorized_findings,
        "failed_tools": failed_tools,
        "security_score_breakdown": security_score_breakdown,

    }
