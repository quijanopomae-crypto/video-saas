from jsonschema import Draft202012Validator
from canonicalization import calculate_manifest_sha256
from asset_resolver import asset_index, resolve_authoritative_asset_kind

def test_full_merged_manifest_pre_freeze(merged_manifest,pre_schema): Draft202012Validator(pre_schema).validate(merged_manifest)
def test_asset_manifest_is_authority(merged_manifest):
    idx=asset_index(merged_manifest['asset_manifest'])
    for rec in merged_manifest['reference_conditioning_cases']:
        for ref in rec['reference_conditioning']['ordered_references']:
            assert resolve_authoritative_asset_kind(ref,idx)==ref['asset_kind']
def test_manifest_hash_deterministic(merged_manifest):
    a=calculate_manifest_sha256(merged_manifest); b=calculate_manifest_sha256(merged_manifest); assert a==b and len(a)==64
