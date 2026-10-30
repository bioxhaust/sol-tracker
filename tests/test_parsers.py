"""Parser tests on real mainnet pool-creation transactions (tests/fixtures/*.json,
captured with `python -m sol_tracker replay ... --save-fixtures tests/fixtures`)."""
import json
from pathlib import Path
import pytest
from sol_tracker.dex import ALL, BY_PROGRAM
from sol_tracker.dex.base import anchor_disc
from sol_tracker.logparse import program_instructions
from sol_tracker.lock import classify, tx_lp_holders
from sol_tracker.price import liquidity_usd, WSOL
from sol_tracker.metadata import metaplex_pda, parse_metaplex

FX = Path(__file__).parent / "fixtures"
WSOL_ = WSOL

# fixture prefix -> expected (dex, instruction, pool, token mint, lp_mint)
EXPECTED = {
    "5ainywe6MEcddaE3": ("raydium_amm_v4", "initialize2"),
    "3UAcCGRdPu8RrMcS": ("raydium_amm_v4", "initialize2"),
    "4y8rM7VguDZEtynm": ("raydium_cpmm", "initialize_with_permission"),
    "2p5LHmgJ2dbRyHSM": ("orca_whirlpool", "initialize_pool_v2"),
    "3paHfqY9HV8CU4MH": ("pumpswap", "create_pool"),
    "daJV4k3bmR7Ky9uK": ("meteora_dlmm", "initialize_lb_pair2"),
    "5hwEAy4Qs143XTFJ": ("meteora_damm_v2", "initialize_customizable_pool"),
    "r2FnKhxLycUnq71Y": ("meteora_damm_v2", "initialize_pool_with_dynamic_config"),
}


def load(prefix):
    return json.loads((FX / f"{prefix}.json").read_text())


def parse_all(tx):
    out = []
    for d in ALL.values():
        out += d.parse(tx)
    return out


@pytest.mark.parametrize("prefix,exp", EXPECTED.items())
def test_real_tx_parses(prefix, exp):
    tx = load(prefix)
    pools = parse_all(tx)
    assert len(pools) == 1, pools
    p = pools[0]
    assert (p.dex, p.instruction) == exp
    keys = set(ALL[p.dex].account_keys(tx))
    for a in (p.pool, p.mint_a, p.mint_b, p.vault_a, p.vault_b):
        assert a in keys
    assert p.mint_a != p.mint_b
    # vaults must hold the two mints in postTokenBalances (proves index mapping)
    kl = ALL[p.dex].account_keys(tx)
    bal = {kl[b["accountIndex"]]: b["mint"] for b in tx["meta"]["postTokenBalances"]}
    if p.dex != "meteora_damm_v1":
        assert bal.get(p.vault_a) == p.mint_a and bal.get(p.vault_b) == p.mint_b
    if ALL[p.dex].lock_model == "lp":
        assert p.lp_mint
    # log prefilter agrees with the instruction decoder
    names = program_instructions(tx["meta"]["logMessages"], ALL[p.dex].program_id)
    assert ALL[p.dex].wants(names)


def test_pumpswap_reserves():
    p = parse_all(load("3paHfqY9HV8CU4MH"))[0]
    # this (user-created) pool has WSOL as base, token as quote
    assert WSOL_ in (p.mint_a, p.mint_b) and min(p.reserve_a, p.reserve_b) > 100


def test_logparse_ignores_cpi_child_logs():
    pid = ALL["pumpswap"].program_id
    logs = [f"Program {pid} invoke [1]", "Program log: Instruction: Buy",
            "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA invoke [2]",
            "Program log: Instruction: InitializeAccount",
            "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA success",
            f"Program {pid} success"]
    assert program_instructions(logs, pid) == ["Buy"]
    assert not ALL["pumpswap"].wants(program_instructions(logs, pid))


def test_non_init_swaps_ignored():
    for prefix in EXPECTED:
        tx = load(prefix)
        for d in ALL.values():
            for p in d.parse(tx):
                assert p.dex == EXPECTED[prefix][0]


def test_discriminators_match_idl_convention():
    assert anchor_disc("create_pool").hex() == "e992d18ecf6840bc"
    assert ALL["raydium_amm_v4"].layouts[0].discriminator == b"\x01"


def test_program_ids_unique():
    assert len(BY_PROGRAM) == len(ALL)


def test_lock_classify():
    inc = "1nc1nerator11111111111111111111111111111111"
    assert classify([(100, inc, None)], 100).status == "burned"
    r = classify([(60, "PDA", "strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m"), (40, inc, None)], 100)
    assert r.status == "locked" and r.lockers == ["streamflow"]
    r = classify([(70, "Wallet", "11111111111111111111111111111111"), (30, inc, None)], 100)
    assert r.status == "unlocked" and round(r.unlocked_pct) == 70
    assert classify([], 0).status == "burned"
    assert classify([(1, "w", None)], 100).status == "unknown"


def test_tx_lp_holders_cpmm():
    tx = load("4y8rM7VguDZEtynm")
    p = parse_all(tx)[0]
    hs = tx_lp_holders(tx, p.lp_mint)
    assert hs and all(a >= 0 for a, _ in hs)


def test_liquidity_usd():
    assert liquidity_usd(WSOL_, 10, "X", 1e6, 200, None) == 4000
    assert liquidity_usd("X", 1, "Y", 2, None, None) is None
    assert liquidity_usd(WSOL_, 1, "U", 100, 200, 1) == 300


def test_metaplex_pda_known():
    # metadata PDA of USDC (verifiable on any explorer)
    assert metaplex_pda("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v") == \
        "5x38Kp4hvdomTCnCrAny4UtMUt5rQBdB6px2K1Ui45Wq"


def test_parse_metaplex():
    def s(x):
        return len(x).to_bytes(4, "little") + x
    data = b"\x04" + b"\x00" * 64 + s(b"Dog\x00\x00") + s(b"DOG\x00")
    assert parse_metaplex(data) == ("Dog", "DOG")
