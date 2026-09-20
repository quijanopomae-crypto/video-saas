from reference_conditioning import ManifestValidationError

def asset_index(asset_manifest): return {a['asset_id']:a for a in asset_manifest['assets']}

def resolve_authoritative_asset_kind(reference, asset_manifest_by_id):
    aid=reference['asset_id']
    if aid not in asset_manifest_by_id: raise ManifestValidationError(f'{aid}: absent from Asset Manifest')
    authoritative=asset_manifest_by_id[aid]['asset_kind']
    if reference['asset_kind']!=authoritative: raise ManifestValidationError(f"{aid}: reference asset_kind={reference['asset_kind']}; Asset Manifest asset_kind={authoritative}")
    return authoritative
