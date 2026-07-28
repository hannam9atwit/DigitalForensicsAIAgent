"""
ai/accounts.py

Which user accounts does the evidence actually establish?

"Who is the user on this machine?" is one of the first questions an examiner
asks, and it is the question a language model is most tempted to answer from
pattern rather than from evidence. So the answer is derived here, deterministically,
from records the parsers already produced — never generated:

  * disk images   — profile directories in the filesystem listing
                    (Users/<name>, Documents and Settings/<name>, /home/<name>)
  * registry      — profile and account records the registry parser emits
  * event logs    — the account a sign-in or service event names

Everything returned carries the records it came from, so a knowledge-base entry
built from it is citable and an examiner can check it. When nothing establishes
an account, that is returned as an empty result and stated as such — the one
answer a model must never improve on.

Pure text over already-parsed events: no Qt, no network, no disk access, so it
unit-tests headless.
"""

import re
from collections import OrderedDict

# Profile roots, lowercased, mapped to how many path segments precede the name.
_PROFILE_ROOTS = ("users", "documents and settings", "home")

# Directory names that sit in a profile root but are not a person's account.
# Windows ships these on every install; reporting them as "the user" would be
# as wrong as inventing a name.
_NOT_ACCOUNTS = {
    "public", "default", "default user", "all users", "defaultapppool",
    "desktop.ini", ".", "..", "administrator.old", "temp", "tempuser",
}

# Well-known Windows service accounts. Real accounts, but never the subject of
# an investigation, so they are reported separately rather than mixed in.
_SERVICE_ACCOUNTS = {
    "system", "local service", "network service", "localsystem", "anonymous logon",
    "dwm-1", "dwm-2", "umfd-0", "umfd-1", "iusr", "trustedinstaller",
}

_ACCOUNT_FIELDS = ("account", "user", "username", "user_name", "subject_user")

# "Account: jdoe", "User Name: jdoe", "for account jdoe" in a parser's label.
_LABEL_ACCOUNT = re.compile(
    r"(?:account|user(?:\s*name)?)\s*[:=]\s*([A-Za-z0-9._$\-]{1,64})", re.IGNORECASE)

_MAX_SAMPLES = 3


def _clean(name):
    name = (name or "").strip().strip("\\/").strip()
    # DOMAIN\user and user@domain both reduce to the account itself.
    if "\\" in name:
        name = name.rsplit("\\", 1)[-1]
    if "@" in name:
        name = name.split("@", 1)[0]
    return name.strip()


def _is_account(name):
    lowered = name.lower()
    if not name or len(name) > 64:
        return False
    if lowered in _NOT_ACCOUNTS:
        return False
    if "." in name and lowered.rsplit(".", 1)[-1] in (
            "ini", "log", "dat", "tmp", "db", "txt", "lnk"):
        return False        # a file that happens to sit in the profile root
    # A profile directory name; letters, digits and the few punctuation marks
    # Windows and Linux allow in an account name.
    return bool(re.fullmatch(r"[A-Za-z0-9._$ \-]{1,64}", name))


def _from_path(path):
    """The account a filesystem path attributes to, or None.

    Handles both separators and tolerates the leading volume marker SleuthKit
    emits, so "/Users/jdoe/Documents/x.docx" and "Users\\jdoe\\x.docx" both
    resolve to "jdoe".
    """
    if not path:
        return None
    parts = [p for p in re.split(r"[\\/]+", str(path)) if p]
    for index, part in enumerate(parts[:-1]):
        if part.lower() in _PROFILE_ROOTS:
            candidate = _clean(parts[index + 1])
            return candidate if _is_account(candidate) else None
    return None


def _from_fields(event):
    for field in _ACCOUNT_FIELDS:
        candidate = _clean(event.get(field))
        if candidate and _is_account(candidate):
            return candidate
    match = _LABEL_ACCOUNT.search(str(event.get("label") or ""))
    if match:
        candidate = _clean(match.group(1))
        if _is_account(candidate):
            return candidate
    return None


def extract(events):
    """Accounts the supplied events establish.

    Returns an OrderedDict, busiest account first:

        {"jdoe": {"records": 412,
                  "sources": ["Disk", "Registry"],
                  "samples": ["/Users/jdoe/Documents/notes.docx", ...],
                  "artifacts": ["EV-01"],
                  "service": False}}

    An empty dict means the evidence does not establish an account — a result,
    not a failure, and one callers must report rather than fill.
    """
    found = {}
    for event in events or []:
        if not isinstance(event, dict):
            continue
        name = _from_fields(event) or _from_path(event.get("path"))
        if not name:
            continue
        key = name.lower()
        entry = found.setdefault(key, {
            "name": name, "records": 0, "sources": set(),
            "samples": [], "artifacts": set(),
            "service": key in _SERVICE_ACCOUNTS,
        })
        entry["records"] += 1
        if event.get("source"):
            entry["sources"].add(str(event["source"]))
        if event.get("artifact"):
            entry["artifacts"].add(str(event["artifact"]))
        sample = event.get("path") or event.get("label")
        if sample and len(entry["samples"]) < _MAX_SAMPLES:
            text = str(sample)
            if text not in entry["samples"]:
                entry["samples"].append(text)

    ordered = OrderedDict()
    for entry in sorted(found.values(),
                        key=lambda e: (e["service"], -e["records"], e["name"])):
        ordered[entry["name"]] = {
            "records":   entry["records"],
            "sources":   sorted(entry["sources"]),
            "samples":   list(entry["samples"]),
            "artifacts": sorted(entry["artifacts"]),
            "service":   entry["service"],
        }
    return ordered


def brief(accounts):
    """One prompt-ready block describing the accounts, or an explicit statement
    that none was established.

    This is what gets handed to a model, so it is deliberately blunt about the
    empty case: a model given "no accounts" and no instruction will supply a
    plausible one.
    """
    if not accounts:
        return ("Accounts established by this evidence: NONE. No profile "
                "directory, registry profile record or account-bearing log entry "
                "was recovered. Do not name a user account anywhere in your "
                "answer; state that the evidence does not establish one.")

    lines = ["Accounts established by this evidence (use these names verbatim, "
             "and no others):"]
    for name, detail in accounts.items():
        kind = "built-in service account" if detail["service"] else "user account"
        source = ", ".join(detail["sources"]) or "unattributed records"
        line = (f"- {name} ({kind}) — {detail['records']:,} records via {source}")
        if detail["samples"]:
            line += f"; e.g. {detail['samples'][0]}"
        lines.append(line)
    return "\n".join(lines)


def summary_sentence(accounts):
    """A deterministic, citable statement of who the evidence shows — the text a
    knowledge-base entry stores so 'who is the user?' is answered from records
    rather than from a model's prior."""
    people = [name for name, detail in accounts.items() if not detail["service"]]
    service = [name for name, detail in accounts.items() if detail["service"]]

    if not people and not service:
        return ("The evidence does not establish any user account. No profile "
                "directory, registry profile record or account-bearing log entry "
                "was recovered from the artifacts in this case, so activity here "
                "cannot be attributed to a named account. A registry hive (SAM or "
                "the ProfileList key) or a Security event log would establish it.")

    parts = []
    if people:
        listed = ", ".join(
            f"{name} ({accounts[name]['records']:,} records)" for name in people)
        verb = "account is" if len(people) == 1 else "accounts are"
        parts.append(f"The user {verb} {listed}.")
        first = people[0]
        if accounts[first]["samples"]:
            parts.append(f"The attribution comes from records such as "
                         f"{accounts[first]['samples'][0]}.")
    if service:
        parts.append("Built-in service accounts also appear: "
                     + ", ".join(service) + ".")
    if not people and service:
        parts.append("No human user account was established; only built-in "
                     "service accounts are present.")
    return " ".join(parts)
