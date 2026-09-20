import copy, hashlib, json, unicodedata
from decimal import Decimal, InvalidOperation

class CanonicalizationError(ValueError): pass

def canonical_decimal(value):
    if not isinstance(value, str): raise CanonicalizationError('canonical decimal must be a JSON string')
    try: d=Decimal(value)
    except InvalidOperation as exc: raise CanonicalizationError(f'invalid decimal: {value!r}') from exc
    if not d.is_finite(): raise CanonicalizationError('non-finite decimal')
    if d == 0: canonical='0'
    else:
        canonical=format(d.normalize(),'f')
        if '.' in canonical: canonical=canonical.rstrip('0').rstrip('.')
        if canonical=='-0': canonical='0'
    if canonical != value: raise CanonicalizationError(f'non-canonical decimal representation: {value!r}; expected {canonical!r}')
    return value

def _nfc(s): return unicodedata.normalize('NFC',s)

def canonicalize_tree(value):
    if value is None or isinstance(value,bool): return value
    if isinstance(value,int): return value
    if isinstance(value,float): raise CanonicalizationError('binary floats are forbidden in hash material')
    if isinstance(value,Decimal): raise CanonicalizationError('Decimal objects are forbidden in hash material')
    if isinstance(value,str): return _nfc(value)
    if isinstance(value,dict):
        out={}
        for k,v in value.items():
            if not isinstance(k,str): raise CanonicalizationError('object keys must be strings')
            nk=_nfc(k)
            if nk in out: raise CanonicalizationError(f'NFC key collision: {k!r} -> {nk!r}')
            out[nk]=canonicalize_tree(v)
        return out
    if isinstance(value,(list,tuple)): return [canonicalize_tree(x) for x in value]
    raise CanonicalizationError(f'unsupported manifest type: {type(value).__name__}')

def canonical_manifest_bytes(manifest):
    canonical=canonicalize_tree(copy.deepcopy(manifest))
    return json.dumps(canonical,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')

def calculate_manifest_sha256(manifest): return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()
