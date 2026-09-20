from asset_resolver import asset_index

def test_known_authoritative_kinds(merged_manifest):
    idx=asset_index(merged_manifest['asset_manifest'])
    expected={
      'A01-A02-office-composite-v1':'COMPOSITE_REFERENCE',
      'P01-P03-kitchen-composite-v1':'COMPOSITE_REFERENCE',
      'M01-walk-stop-keyframe-v1':'MOTION_REFERENCE',
      'MC01-camera-orbit-keyframe-v1':'MOTION_REFERENCE',
      'TEXT-launch-24-sept-v1':'TEXT_REFERENCE',
      'CF-B007-v1':'CANONICAL_FIRST_FRAME',
    }
    for aid,kind in expected.items(): assert idx[aid]['asset_kind']==kind
