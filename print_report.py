import json, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('audit_nytimes.json', encoding='utf-8') as f:
    r = json.load(f)

print(f'site: {r["site"]}')
print(f'audited_at: {r["audited_at"]}')
print(f'total_findings: {r["summary"]["total_findings"]}  critical={r["summary"]["critical"]} high={r["summary"]["high"]} medium={r["summary"]["medium"]} low={r["summary"]["low"]}')
print()
print('=== FINDINGS ===')
for finding in r['findings']:
    print(f'  [{finding["id"]}] [{finding["severity"].upper():8}] {finding["title"]}')
    print(f'       category={finding.get("category","N/A")} source={finding.get("skill_source","N/A")}')
print()

# Schema validation
required = ['id','title','severity','evidence','suggested_action']
for i, finding in enumerate(r['findings']):
    for field in required:
        assert field in finding, f'Finding {i} missing: {field}'
    assert 'summary' in finding['suggested_action']
    assert 'priority' in finding['suggested_action']
print('SCHEMA VALIDATION: PASSED')
