import hashlib
import json
from datetime import datetime, timezone

class HashChain:
    def __init__(self):
        self.genesis_hash = "0" * 64

    def compute_hash(self, entry: dict) -> str:
        clean = {k: v for k, v in entry.items() if k != "hash"}
        canonical = json.dumps(clean, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def build_entry(self, event_type: str, payload: dict, previous_hash: str) -> dict:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": payload,
            "previous_hash": previous_hash,
        }
        entry["hash"] = self.compute_hash(entry)
        return entry

    def verify_chain(self, entries: list) -> tuple:
        for i, entry in enumerate(entries):
            stored_hash = entry.get("hash")
            recomputed = self.compute_hash(entry)

            if recomputed != stored_hash:
                return False, i

            if i > 0 and entry["previous_hash"] != entries[i - 1]["hash"]:
                return False, i

        return True, None
