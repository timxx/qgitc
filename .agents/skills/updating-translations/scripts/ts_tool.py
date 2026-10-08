#!/usr/bin/env python3
"""List, fill and compile the untranslated entries of a Qt Linguist .ts file.

The lupdate-generated document is never reformatted: only the <translation>
element of the entries named by a translations file is rewritten, so contexts,
sources, locations and indentation stay exactly as lupdate wrote them.

Commands:
    stats   <tsFile>
    pending <tsFile> [--output <jsonFile>] [--neighbors <count>] [--stdout]
    apply   <tsFile> <translationsFile>
    build   <translationsDir>

Entry keys are the *unescaped* XML text: a source of '&amp;Soft' is the key
'&Soft', which is what pending writes and what apply expects back.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from xml.sax.saxutils import escape as escapeXml
from xml.sax.saxutils import unescape as unescapeXml

CONTEXT_PATTERN = re.compile(r"<context>(.*?)</context>", re.DOTALL)
NAME_PATTERN = re.compile(r"<name>(.*?)</name>", re.DOTALL)
MESSAGE_PATTERN = re.compile(r"<message>(.*?)</message>", re.DOTALL)
SOURCE_PATTERN = re.compile(r"<source>(.*?)</source>", re.DOTALL)
LOCATION_PATTERN = re.compile(r'<location filename="([^"]*)"(?: line="(\d+)")?\s*/>')
TRANSLATION_PATTERN = re.compile(
    r"<translation(?P<attrs>[^>]*)>(?P<body>.*?)</translation>", re.DOTALL)
DROPPED_TYPE_PATTERN = re.compile(r'type="(?:vanished|obsolete)"')

# Key sequences are shown as-is in every language; Qt falls back to the source
# text when the translation stays empty.
KEY_SEQUENCE_PATTERN = re.compile(
    r"^(?:F\d{1,2}|(?:Ctrl|Shift|Alt|Meta|Cmd)(?:\+(?:Ctrl|Shift|Alt|Meta|Cmd))*\+"
    r"(?:F\d{1,2}|[A-Za-z0-9]|Enter|Return|Esc|Escape|Tab|Space|Del|Delete|Ins|Insert|"
    r"Home|End|PgUp|PgDn|PageUp|PageDown|Backspace|Left|Right|Up|Down))$",
    re.IGNORECASE)


def readText(path):
    with open(path, "rb") as stream:
        return stream.read().decode("utf-8-sig")


def writeText(path, text):
    with open(path, "wb") as stream:
        stream.write(text.encode("utf-8"))


def parseEntries(text):
    entries = []
    for contextMatch in CONTEXT_PATTERN.finditer(text):
        contextBody = contextMatch.group(1)
        contextOffset = contextMatch.start(1)
        nameMatch = NAME_PATTERN.search(contextBody)
        contextName = unescapeXml(nameMatch.group(1)) if nameMatch else ""
        for messageMatch in MESSAGE_PATTERN.finditer(contextBody):
            body = messageMatch.group(1)
            bodyOffset = contextOffset + messageMatch.start(1)
            sourceMatch = SOURCE_PATTERN.search(body)
            if not sourceMatch:
                continue
            translationMatch = TRANSLATION_PATTERN.search(body)
            attrs = translationMatch.group("attrs") if translationMatch else ""
            translation = None
            if translationMatch:
                translation = unescapeXml(translationMatch.group("body"))
            entries.append({
                "context": contextName,
                "source": unescapeXml(sourceMatch.group(1)),
                "translation": translation,
                "attrs": attrs,
                "start": bodyOffset + translationMatch.start() if translationMatch else None,
                "end": bodyOffset + translationMatch.end() if translationMatch else None,
                "locations": [f"{name}:{line}" if line else name
                              for name, line in LOCATION_PATTERN.findall(body)],
            })
    return entries


def isPending(entry):
    if DROPPED_TYPE_PATTERN.search(entry["attrs"]):
        return False
    if "unfinished" in entry["attrs"]:
        return True
    return not (entry["translation"] or "").strip()


def summarize(entries):
    usable = [entry for entry in entries if not DROPPED_TYPE_PATTERN.search(entry["attrs"])]
    pending = [entry for entry in usable if isPending(entry)]
    contexts = {entry["context"] for entry in usable}
    return {
        "contexts": len(contexts),
        "messages": len(usable),
        "translated": len(usable) - len(pending),
        "pending": len(pending),
        "dropped": len(entries) - len(usable),
    }


def collectNeighbors(entries, count):
    byContext = {}
    for entry in entries:
        if isPending(entry) or not (entry["translation"] or "").strip():
            continue
        samples = byContext.setdefault(entry["context"], [])
        if len(samples) < count:
            samples.append({"source": entry["source"], "translation": entry["translation"]})
    return byContext


def defaultOutputPath():
    return os.path.join(tempfile.gettempdir(), "qgitc-translations", "pending.json")


def commandStats(tsPath):
    entries = parseEntries(readText(tsPath))
    counts = summarize(entries)
    print(f"file:       {tsPath}")
    print(f"contexts:   {counts['contexts']}")
    print(f"messages:   {counts['messages']}")
    print(f"translated: {counts['translated']}")
    print(f"pending:    {counts['pending']}")
    print(f"dropped:    {counts['dropped']}")
    for entry in entries:
        if isPending(entry):
            hint = " [key sequence]" if KEY_SEQUENCE_PATTERN.match(entry["source"]) else ""
            print(f"  {entry['context']}: {entry['source']}{hint}")
    return 0


def commandPending(tsPath, outputPath, neighborCount, toStdout):
    entries = parseEntries(readText(tsPath))
    pending = [entry for entry in entries if isPending(entry)]
    payload = {
        "tsFile": tsPath,
        "pendingCount": len(pending),
        "entries": [{
            "context": entry["context"],
            "source": entry["source"],
            "locations": entry["locations"],
            "keySequence": bool(KEY_SEQUENCE_PATTERN.match(entry["source"])),
        } for entry in pending],
        "terminology": collectNeighbors(entries, neighborCount) if neighborCount else {},
    }
    if toStdout:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    if not outputPath:
        outputPath = defaultOutputPath()
    os.makedirs(os.path.dirname(os.path.abspath(outputPath)), exist_ok=True)
    with open(outputPath, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"pending entries: {len(pending)}")
    print(f"pending file:    {os.path.abspath(outputPath)}")
    print(f"translations file to write: "
          f"{os.path.join(os.path.dirname(os.path.abspath(outputPath)), 'translations.json')}")
    return 0


def loadTranslationItems(path):
    with open(path, "r", encoding="utf-8-sig") as stream:
        data = json.load(stream)
    items = data.get("translations") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SystemExit(f"{path}: expected a list, or an object with a 'translations' list")
    return items


def commandApply(tsPath, translationsPath):
    text = readText(tsPath)
    entries = parseEntries(text)
    index = {}
    for entry in entries:
        index.setdefault((entry["context"], entry["source"]), entry)

    edits = []
    unknown = []
    applied = keptEmpty = untouched = 0
    for item in loadTranslationItems(translationsPath):
        if not isinstance(item, dict) or "source" not in item:
            raise SystemExit(f"{translationsPath}: every item needs 'context' and 'source'")
        key = (item.get("context", ""), item["source"])
        entry = index.get(key)
        if entry is None or entry["start"] is None:
            unknown.append(f"{key[0]}\t{key[1]}")
            continue
        translation = item.get("translation")
        if translation is None:
            untouched += 1
            continue
        if translation:
            replacement = f"<translation>{escapeXml(translation)}</translation>"
            applied += 1
        else:
            replacement = "<translation></translation>"
            if isPending(entry):
                keptEmpty += 1
            else:
                untouched += 1
        edits.append((entry["start"], entry["end"], replacement))

    if unknown:
        for line in unknown:
            print(f"unknown entry: {line}", file=sys.stderr)
        print(f"{len(unknown)} key(s) do not match {tsPath}; nothing written", file=sys.stderr)
        return 1

    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    if edits:
        writeText(tsPath, text)

    remaining = [entry for entry in parseEntries(readText(tsPath)) if isPending(entry)]
    print(f"applied:          {applied}")
    print(f"kept empty:       {keptEmpty}")
    print(f"left untouched:   {untouched}")
    print(f"still pending:    {len(remaining)}")
    for entry in remaining:
        hint = " [key sequence]" if KEY_SEQUENCE_PATTERN.match(entry["source"]) else ""
        print(f"  {entry['context']}: {entry['source']}{hint}")
    return 0


def commandBuild(translationsDir):
    directory = os.path.abspath(translationsDir)
    projectPath = os.path.join(directory, "qgitc.json")
    if not os.path.isfile(projectPath):
        print(f"missing {projectPath}", file=sys.stderr)
        return 1
    lrelease = shutil.which("pyside6-lrelease") or shutil.which("lrelease")
    if not lrelease:
        print("Missing lrelease; run 'python setup.py build_qt' instead.", file=sys.stderr)
        return 1
    result = subprocess.run([lrelease, "-project", projectPath], cwd=directory)
    return result.returncode


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subParsers = parser.add_subparsers(dest="command", required=True)

    statsParser = subParsers.add_parser("stats", help="print entry counts and pending sources")
    statsParser.add_argument("tsFile")

    pendingParser = subParsers.add_parser("pending", help="write the pending entries as JSON")
    pendingParser.add_argument("tsFile")
    pendingParser.add_argument("--output", default=None,
                               help="JSON path (default: <temp>/qgitc-translations/pending.json)")
    pendingParser.add_argument("--neighbors", type=int, default=4,
                               help="translated samples kept per context (default: 4)")
    pendingParser.add_argument("--stdout", action="store_true", help="print the JSON instead")

    applyParser = subParsers.add_parser("apply", help="fill translations from a JSON file")
    applyParser.add_argument("tsFile")
    applyParser.add_argument("translationsFile")

    buildParser = subParsers.add_parser("build", help="compile the .qm with lrelease")
    buildParser.add_argument("translationsDir")

    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    if args.command == "stats":
        return commandStats(args.tsFile)
    if args.command == "pending":
        return commandPending(args.tsFile, args.output, args.neighbors, args.stdout)
    if args.command == "apply":
        return commandApply(args.tsFile, args.translationsFile)
    return commandBuild(args.translationsDir)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
