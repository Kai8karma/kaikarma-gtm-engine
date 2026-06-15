"""DNS record string validator for cold-outbound infrastructure.

Validates SPF, DKIM, and DMARC record strings WITHOUT network access — pure
parsing of the record content you already retrieved. This is a pre-flight
check for records you paste in from your DNS provider, not a live-DNS probe.

    python3 02-send-engine/dns_validator.py        # demo
    python3 02-send-engine/test_send.py            # tests

Stdlib only, no network. Rules enforced:
  SPF   — must start 'v=spf1'; must end with '~all' or '-all' (enforced softfail
          or reject); all other endings ('+all', '?all', no 'all') are failures.
  DKIM  — must contain 'v=DKIM1'; must contain a non-empty 'p=' key (the public key).
  DMARC — must start 'v=DMARC1'; must contain a 'p=' policy (none/quarantine/reject).
"""

from __future__ import annotations

from send_schema import DnsCheck


# ---------------------------------------------------------------------------
# SPF
# ---------------------------------------------------------------------------

def _spf_issues(raw: str) -> list[str]:
    issues: list[str] = []
    stripped = raw.strip()

    if not stripped.lower().startswith("v=spf1"):
        issues.append("SPF record must start with 'v=spf1'")

    # Must end with a hard-fail or soft-fail 'all' mechanism.
    # Strip trailing whitespace; check the suffix case-insensitively.
    lower = stripped.lower()
    if lower.endswith("~all") or lower.endswith("-all"):
        pass  # good
    elif lower.endswith("+all"):
        issues.append("'+all' permits anyone to send — use '~all' or '-all'")
    elif lower.endswith("?all"):
        issues.append("'?all' is a neutral result that provides no protection — use '~all' or '-all'")
    else:
        issues.append("SPF record must end with '~all' (softfail) or '-all' (reject)")

    return issues


def validate_spf(raw: str) -> DnsCheck:
    """Validate an SPF TXT record string."""
    issues = _spf_issues(raw)
    return DnsCheck(
        record_type="SPF",
        raw=raw,
        passed=not issues,
        issues=tuple(issues),
    )


# ---------------------------------------------------------------------------
# DKIM
# ---------------------------------------------------------------------------

def _dkim_issues(raw: str) -> list[str]:
    issues: list[str] = []
    stripped = raw.strip()
    lower = stripped.lower()

    if "v=dkim1" not in lower:
        issues.append("DKIM record must include 'v=DKIM1'")

    # Find the p= tag and verify its value is non-empty.
    # Tags are semicolon-delimited; whitespace around tags is allowed.
    p_value = _find_tag_value(stripped, "p")
    if p_value is None:
        issues.append("DKIM record must include a 'p=' public key tag")
    elif p_value == "":
        issues.append("DKIM 'p=' key is empty — this revokes the key; provide the public key value")

    return issues


def _find_tag_value(record: str, tag: str) -> str | None:
    """Return the value of a tag-value pair in a DKIM/DMARC record, or None if absent.

    Tags are semicolon-separated; each tag is `key=value` (whitespace allowed).
    Returns the value string (may be empty string) or None if the tag is not present.
    """
    for part in record.split(";"):
        kv = part.strip()
        if "=" not in kv:
            continue
        k, _, v = kv.partition("=")
        if k.strip().lower() == tag.lower():
            return v.strip()
    return None


def validate_dkim(raw: str) -> DnsCheck:
    """Validate a DKIM TXT record string."""
    issues = _dkim_issues(raw)
    return DnsCheck(
        record_type="DKIM",
        raw=raw,
        passed=not issues,
        issues=tuple(issues),
    )


# ---------------------------------------------------------------------------
# DMARC
# ---------------------------------------------------------------------------

_VALID_DMARC_POLICIES = {"none", "quarantine", "reject"}


def _dmarc_issues(raw: str) -> list[str]:
    issues: list[str] = []
    stripped = raw.strip()

    if not stripped.lower().startswith("v=dmarc1"):
        issues.append("DMARC record must start with 'v=DMARC1'")

    p_value = _find_tag_value(stripped, "p")
    if p_value is None:
        issues.append("DMARC record must include a 'p=' policy tag")
    elif p_value.lower() not in _VALID_DMARC_POLICIES:
        valid = ", ".join(sorted(_VALID_DMARC_POLICIES))
        issues.append(
            f"DMARC 'p={p_value}' is not a valid policy; must be one of: {valid}"
        )

    return issues


def validate_dmarc(raw: str) -> DnsCheck:
    """Validate a DMARC TXT record string."""
    issues = _dmarc_issues(raw)
    return DnsCheck(
        record_type="DMARC",
        raw=raw,
        passed=not issues,
        issues=tuple(issues),
    )


# ---------------------------------------------------------------------------
# Batch convenience
# ---------------------------------------------------------------------------

def validate_all(spf: str, dkim: str, dmarc: str) -> tuple[DnsCheck, DnsCheck, DnsCheck]:
    """Validate all three records in one call. Returns (spf, dkim, dmarc)."""
    return validate_spf(spf), validate_dkim(dkim), validate_dmarc(dmarc)


if __name__ == "__main__":
    samples = [
        ("SPF — good",    "SPF",   "v=spf1 include:sendgrid.net ~all"),
        ("SPF — bad all", "SPF",   "v=spf1 include:sendgrid.net +all"),
        ("SPF — no all",  "SPF",   "v=spf1 include:sendgrid.net"),
        ("DKIM — good",   "DKIM",  "v=DKIM1; k=rsa; p=MIGfMA0GCSq...AQAB"),
        ("DKIM — no key", "DKIM",  "v=DKIM1; k=rsa; p="),
        ("DKIM — no v=",  "DKIM",  "k=rsa; p=MIGfMA0GCSq...AQAB"),
        ("DMARC — good",  "DMARC", "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com"),
        ("DMARC — none p","DMARC", "v=DMARC1; p=none; rua=mailto:dmarc@example.com"),
        ("DMARC — no p=", "DMARC", "v=DMARC1; rua=mailto:dmarc@example.com"),
    ]

    for label, rtype, raw in samples:
        if rtype == "SPF":
            result = validate_spf(raw)
        elif rtype == "DKIM":
            result = validate_dkim(raw)
        else:
            result = validate_dmarc(raw)

        status = "PASS" if result.passed else "FAIL"
        print(f"  {status}  {label}")
        for issue in result.issues:
            print(f"        ↳ {issue}")
