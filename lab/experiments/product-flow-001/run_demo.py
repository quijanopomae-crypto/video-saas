from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from product_flow_lab import ProjectRequest, run_product_flow


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python run_demo.py <request.json>", file=sys.stderr)
        return 2
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    flow = run_product_flow(ProjectRequest.from_dict(payload))
    print(json.dumps(flow.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
