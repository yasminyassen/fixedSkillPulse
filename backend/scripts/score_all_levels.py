"""Print scores for all candidate levels side by side."""
from app.services.code_intelligence import analyze_python_files
from tests.fixtures.candidate_samples import CANDIDATE_LEVELS

for level, code in CANDIDATE_LEVELS.items():
    r = analyze_python_files([{"path": f"app/{level}.py", "content": code}])
    s = r["scores"]
    m = r["aggregate_metrics"]
    print(f"\n=== {level} ===")
    print(f"  scores: CQ={s['code_quality']} MAINT={s['maintainability']} ARCH={s['architecture']} PS={s['problem_solving']} overall={s['overall_score']}")
    print(f"  metrics: cyclomatic={m.get('avg_cyclomatic_complexity',0):.1f} halstead={m.get('avg_halstead_volume',0):.0f} "
          f"types={m.get('avg_type_annotation_coverage',0):.2f} class_types={m.get('avg_class_type_coverage',0):.2f} "
          f"weak_hints={m.get('weak_type_hints',0)} dangerous={m.get('dangerous_patterns',0)} "
          f"globals={m.get('global_keywords',0)} magic={m.get('magic_numbers',0)} "
          f"error_dicts={m.get('error_dict_returns',0)} raises={m.get('explicit_raises',0)} "
          f"depends={m.get('depends_usage',0) if 'depends_usage' in m else 'n/a'} "
          f"repos={m.get('repository_classes',0) if 'repository_classes' in m else 'n/a'} "
          f"classes={m.get('class_count',0)} funcs={m.get('function_count',0)} loc={m.get('total_loc',0)}")
