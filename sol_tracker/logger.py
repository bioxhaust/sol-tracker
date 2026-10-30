import json, logging, sys
from pathlib import Path


def setup(level: str = "INFO") -> logging.Logger:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.basicConfig(level=level, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return logging.getLogger("sol_tracker")


class PoolSink:
    """Structured output: one JSON object per line to stdout and a .jsonl file."""
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "a", buffering=1)

    def emit(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False)
        print(line, flush=True)
        self.f.write(line + "\n")
