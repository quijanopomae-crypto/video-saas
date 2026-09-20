import copy, unicodedata, pytest
from jsonschema import Draft202012Validator
from canonicalization import calculate_manifest_sha256, canonicalize_tree, CanonicalizationError, canonical_decimal

def test_hash_stable(merged_manifest): assert calculate_manifest_sha256(merged_manifest)==calculate_manifest_sha256(merged_manifest)
def test_nfc_nfd_same_hash(merged_manifest):
    a=copy.deepcopy(merged_manifest); b=copy.deepcopy(merged_manifest)
    a['probe_text']='Lucía'; b['probe_text']=unicodedata.normalize('NFD','Lucía')
    assert calculate_manifest_sha256(a)==calculate_manifest_sha256(b)
def test_character_change_changes_hash(merged_manifest):
    a=copy.deepcopy(merged_manifest); b=copy.deepcopy(merged_manifest); a['probe_text']='Lucía'; b['probe_text']='Lucia'
    assert calculate_manifest_sha256(a)!=calculate_manifest_sha256(b)
def test_float_rejected(merged_manifest):
    x=copy.deepcopy(merged_manifest); x['scenario_budgets']['economy']['usd_per_final_accepted_minute']=0.68
    with pytest.raises(CanonicalizationError): calculate_manifest_sha256(x)
def test_nfc_key_collision_rejected():
    a='Lucía'; b=unicodedata.normalize('NFD',a)
    with pytest.raises(CanonicalizationError): canonicalize_tree({a:1,b:2})
@pytest.mark.parametrize('v,ok',[('-0',False),('0',True),('0.0',False),('0.40',False),('0.4',True),('1',True),('1.0',False),('-0.4',True)])
def test_canonical_decimal(v,ok):
    if ok: assert canonical_decimal(v)==v
    else:
        with pytest.raises(CanonicalizationError): canonical_decimal(v)
def test_schema_decimal_examples(pre_schema):
    d=pre_schema['$defs']['canonicalDecimal']; val=Draft202012Validator(d)
    for v in ['0','0.4','1','0.68','1.15','-0.4']: assert not list(val.iter_errors(v))
    for v in ['-0','0.0','0.40','1.0','+1','01','1e3']: assert list(val.iter_errors(v))
