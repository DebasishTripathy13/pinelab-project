import logging
from datetime import datetime, timezone
from .chain import HashChain
from . import primary_store
from . import immutable_store

logger = logging.getLogger("sentinelpay.logging.verifier")

chain = HashChain()

async def verify_integrity() -> dict:
    primary_entries = await primary_store.load_all()
    immutable_entries = await immutable_store.load_all()

    primary_ok, primary_break = chain.verify_chain(primary_entries)
    immutable_ok, immutable_break = chain.verify_chain(immutable_entries)

    # Cross-check
    min_len = min(len(primary_entries), len(immutable_entries))
    cross_ok = all(
        primary_entries[i]["hash"] == immutable_entries[i]["hash"]
        for i in range(min_len)
    )
    stores_in_sync = cross_ok and len(primary_entries) == len(immutable_entries)

    result = {
        "primary_intact": primary_ok,
        "primary_break_at": primary_break,
        "immutable_intact": immutable_ok,
        "immutable_break_at": immutable_break,
        "stores_in_sync": stores_in_sync,
        "primary_count": len(primary_entries),
        "immutable_count": len(immutable_entries),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "tampered": not (primary_ok and immutable_ok and stores_in_sync)
    }

    if result["tampered"]:
        logger.critical(f"AUDIT LOG TAMPERING DETECTED: {result}")
    else:
        logger.info(f"Audit log verified: {result['primary_count']} entries, all intact")

    return result
