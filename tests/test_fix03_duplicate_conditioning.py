import copy, pytest
from itertools import product
from reference_conditioning import validate_raw_record_set, ManifestValidationError

def keys():
    ids=[f'B{i:03d}' for i in range(1,11)]+[f'B{i:03d}' for i in range(21,31)]+[f'B{i:03d}' for i in range(61,71)]
    return set(product(ids,{'I2V_ONE','REFERENCE_THREE','REFERENCE_FIVE'}))
def test_duplicate_fails_before_indexing(merged_manifest):
    rows=copy.deepcopy(merged_manifest['reference_conditioning_cases']); rows[-1]=copy.deepcopy(rows[0])
    with pytest.raises(ManifestValidationError): validate_raw_record_set(rows,keys())
def test_unexpected_or_missing_fails(merged_manifest):
    rows=copy.deepcopy(merged_manifest['reference_conditioning_cases']); rows[-1]['case_id']='B999'
    with pytest.raises(ManifestValidationError): validate_raw_record_set(rows,keys())
