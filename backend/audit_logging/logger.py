import asyncio
import logging
from .chain import HashChain
from . import primary_store
from . import immutable_store

logger = logging.getLogger("sentinelpay.logging")

chain = HashChain()
_last_hash: str = chain.genesis_hash
_initialized = False

async def init_logging():
    global _last_hash, _initialized
    immutable_store.init_immutable_store()

    # Recover last hash from primary store
    entries = await primary_store.load_all()
    if entries:
        _last_hash = entries[-1]["hash"]

    _initialized = True
    logger.info(f"Audit logging initialized. Chain length: {len(entries)}, last hash: {_last_hash[:16]}...")

async def log_event(event_type: str, payload: dict) -> str:
    global _last_hash

    if not _initialized:
        await init_logging()

    entry = chain.build_entry(event_type, payload, _last_hash)
    _last_hash = entry["hash"]

    # Write to both stores
    await asyncio.gather(
        primary_store.write_log(entry),
        immutable_store.write_log(entry)
    )

    logger.info(f"Logged event: {event_type} hash={entry['hash'][:16]}...")
    return entry["hash"]
