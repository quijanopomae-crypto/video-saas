from itertools import product
from reference_conditioning import validate_reference_conditioning, assert_no_legacy_fields, validate_raw_record_set

def expected_keys():
    ids=[f'B{i:03d}' for i in range(1,11)]+[f'B{i:03d}' for i in range(21,31)]+[f'B{i:03d}' for i in range(61,71)]
    return set(product(ids,{'I2V_ONE','REFERENCE_THREE','REFERENCE_FIVE'}))
def test_90_real_records(merged_manifest): validate_raw_record_set(merged_manifest['reference_conditioning_cases'],expected_keys())
def test_all_conditionings_semantically_valid(merged_manifest):
    for r in merged_manifest['reference_conditioning_cases']: assert validate_reference_conditioning(r)
def test_no_legacy_fields(merged_manifest): assert assert_no_legacy_fields(merged_manifest)==[]
def test_30_cases(merged_manifest): assert len({r['case_id'] for r in merged_manifest['reference_conditioning_cases']})==30
