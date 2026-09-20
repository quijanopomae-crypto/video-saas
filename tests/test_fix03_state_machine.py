import pytest
from state_machine import transition, InvalidTransition

def test_valid_chain():
    s='MANIFEST_INTERNAL_INTEGRITY_PENDING'
    for n in ['RUNNING_INTERNAL_TESTS','MANIFEST_INTERNAL_INTEGRITY_PASS','READY_FOR_PROVIDER_PREFLIGHT','PROVIDER_PREFLIGHT_PASS','MODEL_MANIFEST_FROZEN','BENCH20_SCREEN_READY']: s=transition(s,n)
    assert s=='BENCH20_SCREEN_READY'
def test_no_skip_to_provider_preflight():
    with pytest.raises(InvalidTransition): transition('MANIFEST_INTERNAL_INTEGRITY_PENDING','READY_FOR_PROVIDER_PREFLIGHT')
