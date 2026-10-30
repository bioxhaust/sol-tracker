"""Extract instruction names a given program logged, honoring the CPI invoke stack
(so an inner `Instruction: InitializeAccount` from the Token program is not attributed
to the DEX)."""
import re

_INVOKE = re.compile(r"^Program (\w+) invoke \[\d+\]$")
_END = re.compile(r"^Program (\w+) (success|failed)")


def program_instructions(logs: list[str], program_id: str) -> list[str]:
    stack: list[str] = []
    out: list[str] = []
    for line in logs:
        m = _INVOKE.match(line)
        if m:
            stack.append(m[1])
            continue
        if _END.match(line):
            if stack:
                stack.pop()
            continue
        if stack and stack[-1] == program_id and line.startswith("Program log: "):
            text = line[len("Program log: "):]
            if text.startswith("Instruction: "):
                out.append(text[len("Instruction: "):].strip())
            elif text.startswith("initialize2"):  # Raydium AMM v4 (non-Anchor) msg!
                out.append("initialize2")
    return out
