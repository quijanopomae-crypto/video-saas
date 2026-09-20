from collections import Counter
from decimal import Decimal

class ManifestValidationError(ValueError): pass

ALLOWED_TREATMENTS={'I2V_ONE':1,'REFERENCE_THREE':3,'REFERENCE_FIVE':5}
LEGACY_FIELDS={'subject_reference_budget','subject_reference_budget_share'}

def validate_reference_conditioning(record):
    treatment=record['treatment_id']; conditioning=record['reference_conditioning']
    allocations=conditioning['subject_allocations']; references=conditioning['ordered_references']
    if treatment not in ALLOWED_TREATMENTS: raise ManifestValidationError(f'unknown treatment {treatment}')
    if len(references)!=ALLOWED_TREATMENTS[treatment]: raise ManifestValidationError(f"{record['case_id']}/{treatment}: wrong reference count")
    ords=[x['ordinal'] for x in references]
    if ords != list(range(1,len(references)+1)): raise ManifestValidationError('ordinals must be contiguous and match array order')
    subjects=[a['subject_id'] for a in allocations]
    if len(subjects)!=len(set(subjects)): raise ManifestValidationError('duplicate subject allocation')
    if sum(a['reference_count'] for a in allocations)!=len(references): raise ManifestValidationError('allocation reference_count sum mismatch')
    if sum(Decimal(a['share']) for a in allocations)!=Decimal('1'): raise ManifestValidationError('allocation share sum must equal 1')
    counts=Counter(r['subject_id'] for r in references)
    alloc={a['subject_id']:a for a in allocations}
    if set(counts)!=set(alloc): raise ManifestValidationError('reference/allocation subjects mismatch')
    for sid,a in alloc.items():
        if counts[sid]!=a['reference_count']: raise ManifestValidationError(f'{sid}: reference_count mismatch')
    asset_ids=[r['asset_id'] for r in references]
    if len(asset_ids)!=len(set(asset_ids)): raise ManifestValidationError('duplicate asset_id within conditioning')
    if treatment=='I2V_ONE':
        r=references[0]
        if r['asset_kind']!='CANONICAL_FIRST_FRAME' or r['semantic_role']!='CANONICAL_FIRST_FRAME': raise ManifestValidationError('I2V_ONE requires canonical first frame')
    return True

def assert_no_legacy_fields(value,path=()):
    violations=[]
    if isinstance(value,dict):
        for k,v in value.items():
            if k in LEGACY_FIELDS: violations.append(path+(k,))
            violations.extend(assert_no_legacy_fields(v,path+(k,)))
    elif isinstance(value,list):
        for i,v in enumerate(value): violations.extend(assert_no_legacy_fields(v,path+(i,)))
    return violations

def validate_raw_record_set(records, expected_keys):
    if len(records)!=90: raise ManifestValidationError(f'expected 90 raw records; found {len(records)}')
    keys=[(r['case_id'],r['treatment_id']) for r in records]
    if len(set(keys))!=len(keys):
        c=Counter(keys); dup=sorted(k for k,n in c.items() if n>1); raise ManifestValidationError(f'duplicate conditioning records: {dup}')
    actual=set(keys)
    if actual!=expected_keys: raise ManifestValidationError({'missing':sorted(expected_keys-actual),'unexpected':sorted(actual-expected_keys)})
    return True
