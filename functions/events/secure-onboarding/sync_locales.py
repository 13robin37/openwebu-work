#!/usr/bin/env python3
"""Build and validate contributor locale catalogs for Secure Onboarding.

The Open WebUI Function must remain a single, self-contained Python file. This
script keeps human-editable JSON catalogs in ``locales/`` and embeds translated
non-core locales into ``secure_onboarding.py`` for deployment.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_PATH = ROOT / "secure_onboarding.py"
LOCALES_DIR = ROOT / "locales"
GENERATED_START = "# BEGIN GENERATED LOCALE DATA"
GENERATED_END = "# END GENERATED LOCALE DATA"
ADMIN_START = "/*__ADMIN_ONLY_START__*/"
ADMIN_END = "/*__ADMIN_ONLY_END__*/"

STRING = r"'(?:\\.|[^'\\])*'"
PAIR_RE = re.compile(rf"L\(\s*({STRING})\s*,\s*({STRING})\s*\)", re.DOTALL)

BASE_META = {
    "en": {"code": "en", "name": "English", "native_name": "English"},
    "fr": {"code": "fr", "name": "French", "native_name": "Français"},
}


class LocaleError(RuntimeError):
    pass


def _decode(literal: str) -> str:
    value = ast.literal_eval(literal)
    if not isinstance(value, str):
        raise LocaleError("Translation arguments must be string literals")
    return value


def _message_id(french: str, english: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", english.lower()).strip("_")[:48] or "message"
    digest = hashlib.sha256(f"{french}\0{english}".encode("utf-8")).hexdigest()[:10]
    return f"{slug}__{digest}"


def extract_messages(source: str) -> dict[str, tuple[str, str]]:
    messages: dict[str, tuple[str, str]] = {}
    for match in PAIR_RE.finditer(source):
        french = _decode(match.group(1))
        english = _decode(match.group(2))
        message_id = _message_id(french, english)
        pair = (french, english)
        previous = messages.get(message_id)
        if previous is not None and previous != pair:
            raise LocaleError(f"Generated locale ID collision: {message_id}")
        messages[message_id] = pair
    if not messages:
        raise LocaleError("No L('fr', 'en') translation pairs were found")
    return dict(sorted(messages.items()))


def extract_admin_pairs(source: str) -> set[tuple[str, str]]:
    pattern = re.compile(
        rf"{re.escape(ADMIN_START)}(.*?){re.escape(ADMIN_END)}",
        re.DOTALL,
    )
    blocks = pattern.findall(source)
    admin_pairs: set[tuple[str, str]] = set()
    for block in blocks:
        for match in PAIR_RE.finditer(block):
            admin_pairs.add((_decode(match.group(1)), _decode(match.group(2))))
    public_source = pattern.sub("", source)
    public_pairs = {
        (_decode(match.group(1)), _decode(match.group(2)))
        for match in PAIR_RE.finditer(public_source)
    }
    return admin_pairs - public_pairs


def catalog(meta: dict[str, str], messages: dict[str, tuple[str, str]], index: int) -> dict:
    return {
        "_meta": meta,
        "messages": {message_id: pair[index] for message_id, pair in messages.items()},
    }


def _json_text(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _load_catalog(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocaleError(f"Cannot read {path.name}: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("_meta"), dict) or not isinstance(value.get("messages"), dict):
        raise LocaleError(f"{path.name} must contain _meta and messages objects")
    return value


def validate_catalog(path: Path, value: dict, expected_ids: set[str]) -> tuple[str, str, dict[str, str]]:
    meta = value["_meta"]
    code = str(meta.get("code") or "").strip().lower().replace("_", "-")
    native_name = str(meta.get("native_name") or meta.get("name") or code.upper()).strip()
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?", code):
        raise LocaleError(f"{path.name} has an invalid locale code: {code!r}")
    if path.stem != code:
        raise LocaleError(f"{path.name} must use the same code in _meta.code")
    if not native_name:
        raise LocaleError(f"{path.name} needs _meta.native_name")

    raw_messages = value["messages"]
    unknown = sorted(set(raw_messages) - expected_ids)
    missing = sorted(expected_ids - set(raw_messages))
    if unknown:
        raise LocaleError(f"{path.name} has {len(unknown)} unknown message IDs; first: {unknown[0]}")
    if missing:
        raise LocaleError(f"{path.name} is missing {len(missing)} messages; first: {missing[0]}")

    translations: dict[str, str] = {}
    for message_id, translated in raw_messages.items():
        if not isinstance(translated, str) or not translated.strip():
            raise LocaleError(f"{path.name} has an empty translation for {message_id}")
        translations[message_id] = translated
    return code, native_name, translations


def generated_block(
    messages: dict[str, tuple[str, str]],
    catalogs: list[tuple[str, str, dict[str, str]]],
    admin_pairs: set[tuple[str, str]],
) -> str:
    names = {"fr": "Français", "en": "English"}
    extra: dict[str, dict[str, str]] = {}
    codes = ["fr", "en"]
    for code, native_name, translations in sorted(catalogs, key=lambda item: item[0]):
        if code in {"fr", "en"}:
            continue
        codes.append(code)
        names[code] = native_name
        extra[code] = {
            f"{french}\x1f{english}": translations[message_id]
            for message_id, (french, english) in messages.items()
        }

    return (
        f"{GENERATED_START}\n"
        f"SUPPORTED_LOCALES = {tuple(codes)!r}\n"
        f"LOCALE_NAMES = {json.dumps(names, ensure_ascii=False, sort_keys=True)}\n"
        f"EXTRA_LOCALE_TRANSLATIONS = {json.dumps(extra, ensure_ascii=False, sort_keys=True)}\n"
        f"ADMIN_LOCALE_KEYS = {tuple(sorted(f'{french}\x1f{english}' for french, english in admin_pairs))!r}\n"
        f"{GENERATED_END}"
    )


def replace_generated_block(source: str, block: str) -> str:
    pattern = re.compile(
        rf"{re.escape(GENERATED_START)}.*?{re.escape(GENERATED_END)}",
        re.DOTALL,
    )
    if not pattern.search(source):
        raise LocaleError("Generated locale markers are missing from secure_onboarding.py")
    return pattern.sub(lambda _match: block, source, count=1)


def run(check: bool) -> int:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    messages = extract_messages(source)
    admin_pairs = extract_admin_pairs(source)
    expected_ids = set(messages)
    expected_base = {
        "en": catalog(BASE_META["en"], messages, 1),
        "fr": catalog(BASE_META["fr"], messages, 0),
    }

    errors: list[str] = []
    if check:
        for code, value in expected_base.items():
            path = LOCALES_DIR / f"{code}.json"
            try:
                actual = _load_catalog(path)
            except LocaleError as exc:
                errors.append(str(exc))
                continue
            if actual != value:
                errors.append(f"{path.name} is stale; run: python sync_locales.py")
    else:
        LOCALES_DIR.mkdir(parents=True, exist_ok=True)
        for code, value in expected_base.items():
            (LOCALES_DIR / f"{code}.json").write_text(_json_text(value), encoding="utf-8")

    translated_catalogs: list[tuple[str, str, dict[str, str]]] = []
    if LOCALES_DIR.exists():
        for path in sorted(LOCALES_DIR.glob("*.json")):
            if path.stem in {"en", "fr"}:
                continue
            try:
                value = _load_catalog(path)
                translated_catalogs.append(validate_catalog(path, value, expected_ids))
            except LocaleError as exc:
                errors.append(str(exc))

    block = generated_block(messages, translated_catalogs, admin_pairs)
    updated_source = replace_generated_block(source, block)
    if check:
        if updated_source != source:
            errors.append("Embedded locale data is stale; run: python sync_locales.py")
    elif updated_source != source:
        SOURCE_PATH.write_text(updated_source, encoding="utf-8")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    action = "validated" if check else "synchronized"
    print(f"{action} {len(messages)} messages across {2 + len(translated_catalogs)} locales")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate without changing files")
    args = parser.parse_args()
    try:
        return run(args.check)
    except LocaleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
