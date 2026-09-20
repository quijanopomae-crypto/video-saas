import sys, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import pytest
from manifest_merge import load_merged_manifest
@pytest.fixture
def root(): return ROOT
@pytest.fixture
def merged_manifest(): return load_merged_manifest()
@pytest.fixture
def pre_schema(root): return json.loads((root/'schemas/pre-asset-freeze.schema.json').read_text())
@pytest.fixture
def frozen_schema(root): return json.loads((root/'schemas/frozen-manifest.schema.json').read_text())
