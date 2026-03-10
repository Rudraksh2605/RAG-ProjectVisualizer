"""Quick test for the security scanner JSON parsing and summary logic."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generators.security_scanner import _parse_findings, compute_scan_summary

# Test 1: Clean JSON array
test1 = _parse_findings(
    '[{"severity":"HIGH","title":"Hardcoded API key",'
    '"location":"ApiClient.java","description":"Found key",'
    '"recommendation":"Use BuildConfig"}]'
)
assert len(test1) == 1 and test1[0]["severity"] == "HIGH"
print(f"Test 1 (clean JSON): PASS - {len(test1)} finding(s)")

# Test 2: JSON inside code fences
test2 = _parse_findings(
    'Here are the results:\n```json\n'
    '[{"severity":"CRITICAL","title":"SQL injection",'
    '"location":"Dao.java","description":"raw query",'
    '"recommendation":"use parameterized"}]\n```\nEnd.'
)
assert len(test2) == 1 and test2[0]["severity"] == "CRITICAL"
print(f"Test 2 (fenced JSON): PASS - {len(test2)} finding(s)")

# Test 3: Empty array
test3 = _parse_findings("[]")
assert len(test3) == 0
print(f"Test 3 (empty []): PASS - {len(test3)} finding(s)")

# Test 4: Plain text fallback
test4 = _parse_findings("No issues found in the codebase.")
assert len(test4) == 1 and test4[0]["severity"] == "INFO"
print(f"Test 4 (plain text): PASS - fallback to INFO")

# Test 5: Invalid severity normalization
test5 = _parse_findings('[{"severity":"BANANA","title":"Bad sev"}]')
assert test5[0]["severity"] == "INFO"
print(f"Test 5 (bad severity): PASS - normalized to INFO")

# Test 6: Multiple findings
test6 = _parse_findings(
    '[{"severity":"CRITICAL","title":"A","location":"X","description":"d","recommendation":"r"},'
    '{"severity":"LOW","title":"B","location":"Y","description":"d","recommendation":"r"},'
    '{"severity":"HIGH","title":"C","location":"Z","description":"d","recommendation":"r"}]'
)
assert len(test6) == 3
# Should be sorted by severity: CRITICAL, HIGH, LOW (done in scan_category)
print(f"Test 6 (multiple): PASS - {len(test6)} finding(s)")

# Test 7: Compute summary
summary = compute_scan_summary({
    "cat1": {"findings": test1, "display_name": "Cat1"},
    "cat2": {"findings": test2, "display_name": "Cat2"},
    "cat3": {"findings": [], "display_name": "Cat3"},
})
assert summary["total_findings"] == 2
assert summary["by_severity"]["HIGH"] == 1
assert summary["by_severity"]["CRITICAL"] == 1
assert summary["categories_clean"] == 1
assert summary["categories_scanned"] == 3
assert 0 <= summary["health_score"] <= 100
print(f"Test 7 (summary): PASS - score={summary['health_score']}, "
      f"grade={summary['health_grade']}, total={summary['total_findings']}")

print("\n[PASS] All security scanner tests PASSED!")
