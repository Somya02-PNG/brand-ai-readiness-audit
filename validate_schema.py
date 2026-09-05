import json

with open('audit_example_com.json', encoding='utf-8') as f:
    r = json.load(f)

# Schema validation
assert 'site' in r
assert 'audited_at' in r
assert 'summary' in r
assert 'findings' in r
assert isinstance(r['findings'], list)

required_finding_fields = ['id', 'title', 'severity', 'evidence', 'suggested_action']
for i, finding in enumerate(r['findings']):
    for field in required_finding_fields:
        assert field in finding, f'Finding {i} missing: {field}'
    assert 'summary' in finding['suggested_action']
    assert 'priority' in finding['suggested_action']

print('SCHEMA VALID')
print('site:', r['site'])
print('audited_at:', r['audited_at'])
print('total_findings:', r['summary']['total_findings'])
print('critical:', r['summary']['critical'])
print('high:', r['summary']['high'])
print('medium:', r['summary']['medium'])
print('low:', r['summary']['low'])
print()
print('=== FINDINGS ===')
for finding in r['findings']:
    print(f"  [{finding['id']}] [{finding['severity'].upper():8}] {finding['title']}")
    print(f"       category={finding.get('category','N/A')} source={finding.get('skill_source','N/A')}")
