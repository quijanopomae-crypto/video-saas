import copy
from jsonschema import Draft202012Validator

def replace_pending(value):
    if isinstance(value,dict): return {k:replace_pending(v) for k,v in value.items()}
    if isinstance(value,list): return [replace_pending(v) for v in value]
    if value=='PENDING_ASSET_FREEZE': return 'a'*64
    return value

def test_pre_freeze_allows_pending(merged_manifest,pre_schema): Draft202012Validator(pre_schema).validate(merged_manifest)
def test_frozen_schema_rejects_pending(merged_manifest,frozen_schema): assert list(Draft202012Validator(frozen_schema).iter_errors(merged_manifest))
def test_frozen_schema_accepts_materialized_hash_fields(merged_manifest,frozen_schema):
    x=replace_pending(copy.deepcopy(merged_manifest)); Draft202012Validator(frozen_schema).validate(x)
def test_no_frozen_state_with_pending(merged_manifest):
    assert merged_manifest['current_state']!='MODEL_MANIFEST_FROZEN'
