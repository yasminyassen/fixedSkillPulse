def test_prepare_coverage_report_uses_uploaded_xml(tmp_path):
    from app.services.sonarqube_service import prepare_coverage_report

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    upload_path = tmp_path / "uploaded-coverage.xml"
    upload_path.write_text(
        '<?xml version="1.0" ?><coverage version="7.0"></coverage>',
        encoding="utf-8",
    )

    result = prepare_coverage_report(str(repo_path), uploaded_coverage_path=str(upload_path))

    assert result["status"] == "ready"
    assert result["source"] == "uploaded"
    assert result["coverage_file_exists"] is True
    assert (repo_path / "coverage.xml").exists()


def test_normalize_coverage_xml_paths_rewrites_sources_and_class_filenames(tmp_path):
    import xml.etree.ElementTree as ET

    from app.services.sonarqube_service import normalize_coverage_xml_paths

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "index.py").write_text("print('hello')\n", encoding="utf-8")
    (repo_path / "src").mkdir()
    (repo_path / "src" / "worker.py").write_text("def work():\n    return None\n", encoding="utf-8")
    (repo_path / "pkg").mkdir()
    (repo_path / "pkg" / "request.py").write_text("def request():\n    return None\n", encoding="utf-8")
    coverage_path = repo_path / "coverage.xml"
    coverage_path.write_text(
        """<?xml version="1.0" ?>
<coverage line-rate="0.3243" lines-covered="12" lines-valid="37">
  <sources>
    <source>/app</source>
  </sources>
  <packages>
    <package name=".">
      <classes>
        <class name="index" filename="/app/index.py" line-rate="0.5" />
        <class name="worker" filename="/github/workspace/src/worker.py" line-rate="0.75" />
        <class name="request" filename="request.py" line-rate="0.25" />
      </classes>
    </package>
  </packages>
</coverage>
""",
        encoding="utf-8",
    )

    result = normalize_coverage_xml_paths(str(coverage_path), str(repo_path))

    assert result == {
        "matched_files": 3,
        "unmatched_files": [],
        "ambiguous_files": [],
    }
    root = ET.parse(coverage_path).getroot()
    assert root.get("line-rate") == "0.3243"
    assert root.get("lines-covered") == "12"
    assert root.get("lines-valid") == "37"
    assert root.find("sources/source").text == str(repo_path.resolve())
    filenames = [node.get("filename") for node in root.findall(".//class")]
    assert filenames == ["index.py", "src/worker.py", "pkg/request.py"]


def test_normalize_coverage_xml_paths_reports_unmatched_files(tmp_path):
    from app.services.sonarqube_service import normalize_coverage_xml_paths

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "actual.py").write_text("print('hello')\n", encoding="utf-8")
    coverage_path = repo_path / "coverage.xml"
    coverage_path.write_text(
        """<?xml version="1.0" ?>
<coverage>
  <packages>
    <package name=".">
      <classes>
        <class name="missing" filename="/app/missing.py" />
      </classes>
    </package>
  </packages>
</coverage>
""",
        encoding="utf-8",
    )

    result = normalize_coverage_xml_paths(str(coverage_path), str(repo_path))

    assert result["matched_files"] == 0
    assert result["unmatched_files"] == ["/app/missing.py"]


def test_safe_get_file_measures_returns_forbidden_fallback(monkeypatch):
    import httpx

    from app.services import sonarqube_service

    request = httpx.Request("GET", "http://sonarqube/api/measures/component_tree")
    response = httpx.Response(403, request=request)

    def raise_forbidden(_project_key):
        raise httpx.HTTPStatusError("Forbidden", request=request, response=response)

    monkeypatch.setattr(sonarqube_service, "get_file_measures", raise_forbidden)

    result = sonarqube_service.safe_get_file_measures("project-key")

    assert result["components"] == []
    assert result["unavailable"] is True
    assert result["reason"] == "sonarqube_file_measures_forbidden"
    assert result["status_code"] == 403
