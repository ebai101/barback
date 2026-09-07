from __future__ import annotations

import re
from collections.abc import Iterable

from barback.audio_file import AudioFile
from barback.config import get_config
from barback.util.logger import get_logger
from barback.util.types import Issue


def check_format_sr_bd(af: AudioFile) -> list[Issue]:
    """44.1 kHz, 24‑bit, .wav only."""
    logger = get_logger()
    issues: list[Issue] = []

    ext = af.file_path.suffix.lower()
    if ext != ".wav":
        logger.debug(f"SR/BD: {af.file_path.name} - Not a WAV file ({ext})")
        issues.append(Issue("SR/BD", "not a wav file"))

    if af.sample_rate != 44100:
        logger.debug(
            f"SR/BD: {af.file_path.name} - Incorrect sample rate ({af.sample_rate}Hz)"
        )
        issues.append(
            Issue(
                "SR/BD",
                f"sample rate {af.sample_rate} is incorrect",
            )
        )

    if af.subtype != "PCM_24":
        logger.debug(f"SR/BD: {af.file_path.name} - Incorrect bit depth ({af.subtype})")
        issues.append(
            Issue(
                "SR/BD",
                f"bit depth {af.subtype} is incorrect",
            )
        )

    return issues


def check_silence(af: AudioFile) -> list[Issue]:
    """Silence at start/end of one shots"""
    logger = get_logger()
    issues: list[Issue] = []

    start, end = af.get_start_end_silence()

    name = str(af.file_path)
    if "loop" in name.lower():
        return []

    # Check start
    if start >= 500:
        logger.debug(f"Silence: {af.file_path.name} - {start} samples at the start")
        issues.append(
            Issue("Silence", f"{start} samples at the start"),
        )

    # Check end
    if end >= 22050:
        logger.debug(f"Silence: {af.file_path.name} - {end} samples at the end")
        issues.append(
            Issue("Silence", f"{end} samples at the end"),
        )

    return issues


def check_zero_crossing(af: AudioFile) -> list[Issue]:
    """Clicks/pops at start/end."""
    logger = get_logger()
    issues: list[Issue] = []

    nonzeros = af.get_start_end_zero_crossing()
    if not nonzeros:
        return issues

    logger.debug(f"ZC: {af.file_path.name} - nonzero values at {nonzeros}")
    issues.append(
        Issue("ZC", f"nonzero values at {nonzeros}"),
    )
    return issues


def check_loop(af: AudioFile) -> list[Issue]:
    """
    Loop validity based on BPM/bars/expected samples.

    Uses AudioFile.is_loop(), which already:
    - extracts BPM from filename (regex),
    - computes bar length in samples,
    - compares actual vs expected sample count,
    - returns (is_loop, message, bpm, num_bars).
    """
    logger = get_logger()
    issues: list[Issue] = []

    # If filename does not suggest loop, skip this check
    if "loop" not in str(af.file_path).lower():
        return issues

    resp = af.is_loop()
    if resp.is_loop:
        return issues

    # Non‑loop case: reclassify common messages into structured issues
    msg = resp.response
    if "bpm out of range" in msg:
        logger.debug(f"Loop: {af.file_path.name} - bpm out of range")
        issues.append(Issue("Loop", "does not loop (bpm out of range)"))
    elif "no bpm found" in msg:
        logger.debug(f"Loop: {af.file_path.name} - does not loop (no bpm found)")
        issues.append(Issue("Loop", "does not loop (no bpm found)"))
    elif "off by" in msg:
        logger.debug(f"Loop: {af.file_path.name} - does not loop ({msg})")
        issues.append(Issue("Loop", f"does not loop ({msg})"))
    else:
        logger.debug(f"Loop: {af.file_path.name} - does not loop ({msg})")
        issues.append(Issue("Loop", f"does not loop ({msg})"))

    return issues


_KEY_SIG_REGEX = re.compile(r"_[A-G][b#]?(maj|min)?")
_KEY_SIG_AT_END_REGEX = re.compile(r"^.*_[A-G](?:#|b)?(?:maj|min)?(?:\.wav)?$")


def check_tonal_loop_key_signature(af: AudioFile) -> list[Issue]:
    """Tonal loops should have a key signature at the end of the filename."""
    logger = get_logger()
    issues: list[Issue] = []

    basename = af.file_path.name

    # First: multiple key signatures anywhere
    key_sig_matches = _KEY_SIG_REGEX.findall(basename)
    if len(key_sig_matches) > 1:
        logger.debug(f"Key sig: {af.file_path.name} - multiple key signatures")
        issues.append(Issue("Key sig", "multiple key signatures"))
        # Still continue; filename format may also be wrong.

    if "loop" not in af.file_path.name:
        return issues

    # Only enforce for loops that are not clearly drums/percussion
    if not any(
        s in str(af.file_path).lower() for s in ("drum", "perc", "hihat", "top")
    ) and not _KEY_SIG_AT_END_REGEX.match(basename):
        logger.debug(
            f"Key sig: {af.file_path.name} - does not have a key signature but is a tonal loop"
        )
        issues.append(
            Issue(
                "Key sig",
                "does not have a key signature but is a tonal loop",
            )
        )

    return issues


def validate_audio_file(af: AudioFile) -> list[Issue]:
    """
    Run all validation checks on a single AudioFile.

    Caller is responsible for:
    - constructing AudioFile,
    - calling af.load(mono=True/False) before this,
    - calling af.unload() afterwards.
    """
    logger = get_logger()
    logger.debug(
        f"Starting validation: {af.file_path.name}", extra={"filepath": af.file_path}
    )
    config = get_config()

    issues: list[Issue] = []
    checks: list = [
        (config.repairs.sr_bd.enabled, check_format_sr_bd),
        (config.repairs.silence.enabled, check_silence),
        (config.repairs.microfades.enabled, check_zero_crossing),
        (config.repairs.loop.enabled, check_loop),
        (config.repairs.keysig.enabled, check_tonal_loop_key_signature),
    ]

    for c in checks:
        if c[0]:
            issues.extend(c[1](af))

    if issues:
        issue_summary = ", ".join(f"{i.kind}" for i in issues)
        logger.debug(
            f"Validation complete: {af.file_path.name} - {len(issues)} issue(s): {issue_summary}",
            extra={"filepath": af.file_path, "issues": len(issues)},
        )
    else:
        logger.debug(
            f"Validation complete: {af.file_path.name} - No issues",
            extra={"filepath": af.file_path},
        )

    return issues


def summarize_issues(issues: Iterable[Issue]) -> str:
    """
    Convert a list of FinalizerIssues into a single short string,
    suitable for a table column.
    """
    msgs = [i.message for i in issues]
    return "; ".join(msgs)
