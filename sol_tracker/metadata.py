"""Token symbol: Token-2022 metadata extension (jsonParsed) or Metaplex metadata PDA."""
from __future__ import annotations
import base64, hashlib
from .b58 import b58decode, b58encode

METAPLEX = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"
_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P


def _on_curve(b: bytes) -> bool:
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= _P:
        return False
    y2 = y * y % _P
    x2 = (y2 - 1) * pow(_D * y2 + 1, _P - 2, _P) % _P
    if x2 == 0:
        return True
    return pow(x2, (_P - 1) // 2, _P) == 1


def find_pda(seeds: list[bytes], program: str) -> str:
    pid = b58decode(program)
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + pid + b"ProgramDerivedAddress").digest()
        if not _on_curve(h):
            return b58encode(h)
    raise ValueError("no PDA")


def metaplex_pda(mint: str) -> str:
    return find_pda([b"metadata", b58decode(METAPLEX), b58decode(mint)], METAPLEX)


def parse_metaplex(data: bytes) -> tuple[str, str]:
    o = 1 + 32 + 32
    n = int.from_bytes(data[o:o + 4], "little"); o += 4
    name = data[o:o + n].decode(errors="ignore").rstrip("\x00"); o += n
    n = int.from_bytes(data[o:o + 4], "little"); o += 4
    sym = data[o:o + n].decode(errors="ignore").rstrip("\x00")
    return name.strip(), sym.strip()


async def token_info(rpc, mint: str) -> dict:
    out = {"symbol": None, "name": None}
    try:
        acc = (await rpc.get_multiple_accounts([mint]))[0]
        info = acc["data"]["parsed"]["info"] if acc else {}
        out["decimals"] = info.get("decimals")
        out["mint_authority"] = info.get("mintAuthority")
        out["freeze_authority"] = info.get("freezeAuthority")
        for ext in info.get("extensions") or []:
            if ext.get("extension") == "tokenMetadata":
                out["symbol"] = ext["state"].get("symbol")
                out["name"] = ext["state"].get("name")
                return out
        md = (await rpc.call("getAccountInfo", [metaplex_pda(mint), {"encoding": "base64"}]))["value"]
        if md:
            out["name"], out["symbol"] = parse_metaplex(base64.b64decode(md["data"][0]))
    except Exception:  # noqa: BLE001
        pass
    return out
