"""Match a supplied key-study bibliography without labeling or adding records."""

import csv
import html
import io
import re
import unicodedata
from pathlib import PurePath
from urllib.parse import unquote

import pandas as pd
import rispy

MAX_BYTES = 2 * 1024 * 1024
MAX_ENTRIES = 1000
FIELDS = ("doi", "title", "authors", "year")
ALIASES = {
    "primary_title": "title",
    "article title": "title",
    "author": "authors",
    "first_authors": "authors",
    "publication year": "year",
}


def text(value):
    if isinstance(value, list):
        return "; ".join(text(x) for x in value)
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize_doi(value):
    value = text(value).casefold()
    value = re.sub(r"^doi\s*:\s*", "", value)
    if re.match(r"^https?://(?:dx\.)?doi\.org/", value):
        value = unquote(re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value))
    return value.strip()


def normalize_title(value):
    value = unicodedata.normalize("NFKC", html.unescape(text(value))).casefold()
    return " ".join(re.findall(r"[^\W_]+", value))


def clean_entries(entries):
    if not entries or len(entries) > MAX_ENTRIES:
        raise ValueError(f"Supply between 1 and {MAX_ENTRIES} seed articles.")
    cleaned = []
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise ValueError(f"Seed entry {index} must contain a DOI or title.")
        item = {field: text(entry.get(field)) for field in FIELDS}
        if any(len(value) > 10000 for value in item.values()):
            raise ValueError(f"Seed entry {index} has an excessively long field.")
        if not normalize_title(item["title"]) and not item["doi"]:
            raise ValueError(f"Seed entry {index} has neither a DOI nor a title.")
        if item["doi"] and not re.fullmatch(
            r"10\.\d{4,9}/\S+", normalize_doi(item["doi"])
        ):
            raise ValueError(
                f"Seed entry {index} has an invalid DOI. Correct or clear it."
            )
        cleaned.append(item)
    return cleaned


def parse_file(filename, raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("The seed list must be no larger than 2 MB.")
    suffix = PurePath(filename).suffix.casefold()
    if suffix not in (".csv", ".ris"):
        raise ValueError("Upload a CSV or RIS seed list.")
    try:
        content = raw.decode(
            "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
        )
    except UnicodeDecodeError:
        try:
            content = raw.decode("cp1252")
        except UnicodeDecodeError as err:
            raise ValueError("Save the seed list with UTF-8 encoding.") from err
    try:
        if suffix == ".csv":
            try:
                dialect = csv.Sniffer().sniff(content[:8192], delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(io.StringIO(content), dialect=dialect, strict=True)
            headers = [text(x).casefold() for x in (reader.fieldnames or [])]
            names = [ALIASES.get(x, x) for x in headers]
            if not {"doi", "title"}.intersection(names):
                raise ValueError("CSV needs a 'doi' or 'title' column (or both).")
            if any(names.count(field) > 1 for field in FIELDS):
                raise ValueError(
                    "CSV has duplicate DOI, title, author or year columns."
                )
            entries = []
            for row in reader:
                if None in row:
                    raise ValueError(
                        "CSV has extra values; quote titles containing commas."
                    )
                if any(text(value) for value in row.values()):
                    entries.append(dict(zip(names, row.values(), strict=True)))
        else:
            entries = list(rispy.loads(content, skip_unknown_tags=True))
            starts = len(re.findall(r"^TY  -", content, re.MULTILINE))
            ends = len(re.findall(r"^ER  -", content, re.MULTILINE))
            if starts != ends or starts != len(entries):
                raise ValueError(
                    "RIS has an incomplete record; re-export the seed list."
                )
            entries = [
                {
                    "doi": row.get("doi"),
                    "title": row.get("title") or row.get("primary_title"),
                    "authors": row.get("authors") or row.get("first_authors"),
                    "year": row.get("year") or row.get("publication_year"),
                }
                for row in entries
            ]
    except (csv.Error, TypeError, KeyError) as err:
        raise ValueError(
            "Cannot read the seed list; check its CSV or RIS format."
        ) from err
    return clean_entries(entries)


def match_entries(entries, dataset):
    """Only unambiguous exact DOI/normalized-title matches are automatic."""
    records, doi_index, title_index, group_dois = {}, {}, {}, {}
    for row in dataset.to_dict("records"):
        group = int(row["group_id"])
        record_id = int(row["record_id"])
        record = {field: text(row.get(field)) for field in FIELDS}
        record.update(record_id=record_id, group_id=group)
        if group not in records or record_id == group:
            records[group] = record
        for field, index, normalizer in (
            ("doi", doi_index, normalize_doi),
            ("title", title_index, normalize_title),
        ):
            value = normalizer(record[field])
            if value:
                index.setdefault(value, set()).add(group)
                if field == "doi":
                    group_dois.setdefault(group, set()).add(value)
    result = []
    for index, entry in enumerate(clean_entries(entries)):
        doi = normalize_doi(entry["doi"])
        doi_groups = doi_index.get(doi, set())
        title_groups = title_index.get(normalize_title(entry["title"]), set())
        conflict = bool(
            (doi_groups and title_groups and doi_groups.isdisjoint(title_groups))
            or (
                doi
                and not doi_groups
                and any(
                    group_dois.get(group) and doi not in group_dois[group]
                    for group in title_groups
                )
            )
        )
        candidates = (
            doi_groups | title_groups if conflict else doi_groups or title_groups
        )
        method = "doi" if doi_groups else "title"
        if conflict:
            status, reason = (
                "conflict",
                "DOI and title information conflict. Check the record.",
            )
        elif len(candidates) == 1:
            status, reason = (
                "matched",
                f"Matched by {method.upper() if method == 'doi' else method}.",
            )
        elif candidates:
            status, reason = (
                "ambiguous",
                "More than one study matches. Choose the correct record.",
            )
        else:
            status, reason = (
                "missing",
                "No exact match. Search manually or confirm it is absent.",
            )
        options = [records[group] for group in sorted(candidates)]
        result.append(
            {
                "id": index,
                **entry,
                "status": status,
                "reason": reason,
                "method": method if status == "matched" else None,
                "match": options[0] if status == "matched" else None,
                "candidates": options[:20],
                "candidate_count": len(options),
            }
        )
    return result


def import_audit(payload, dataset, key_groups):
    """Validate all decisions, then record matching and explicit absence claims."""
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise ValueError("Invalid seed import report.")
    entries = payload["entries"]
    matches = match_entries(entries, dataset)
    groups = dict(zip(dataset["record_id"], dataset["group_id"], strict=True))
    audit = []
    for entry, match in zip(entries, matches, strict=True):
        chosen = entry.get("record_id")
        absent = entry.get("not_present") is True
        if absent and chosen is None:
            resolution, group = "not_present", None
        elif not absent and type(chosen) is int and chosen in groups:
            group = int(groups[chosen])
            if group not in key_groups:
                raise ValueError(
                    "An imported seed is missing from the selected key studies."
                )
            resolution = (
                match["method"]
                if match["match"] and match["match"]["group_id"] == group
                else "manual"
            )
        else:
            raise ValueError(
                f"Resolve seed entry {match['id'] + 1} before starting SAFE."
            )
        audit.append(
            {
                **{field: match[field] for field in FIELDS},
                "initial_status": match["status"],
                "resolution": resolution,
                "record_id": chosen,
                "group_id": group,
            }
        )
    return {
        "filename": PurePath(text(payload.get("filename")).replace("\\", "/")).name[
            :255
        ],
        "entries": audit,
    }
