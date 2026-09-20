from pathlib import Path
import json, yaml
ROOT=Path(__file__).resolve().parents[1]

def load_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]

def load_merged_manifest():
    base=yaml.safe_load((ROOT/'manifests/model-manifest-bench100-v1.1.yaml').read_text(encoding='utf-8'))
    base['reference_conditioning_cases']=load_jsonl(ROOT/'manifests/reference-conditioning-cases-v1.1.jsonl')
    base['asset_manifest']=json.loads((ROOT/'manifests/asset-manifest-v1.0.json').read_text(encoding='utf-8'))
    base['applied_amendments']=[
      yaml.safe_load((ROOT/'manifests/preflight-internal-fix-01.yaml').read_text()),
      yaml.safe_load((ROOT/'manifests/preflight-internal-fix-02.yaml').read_text()),
      yaml.safe_load((ROOT/'manifests/preflight-internal-fix-03.yaml').read_text()),
    ]
    return base
