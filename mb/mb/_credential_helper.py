"""Killable platform credential-store worker.

The parent process supplies refs and values as JSON on stdin. This module
emits one small JSON result and never includes raw exception text.
"""

from __future__ import annotations

import contextlib
import ctypes
import importlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SERVICE_NAME = "mainbranch"
ERR_SEC_SUCCESS = 0
ERR_SEC_DUPLICATE_ITEM = -25299
ERR_SEC_ITEM_NOT_FOUND = -25300
ERR_SEC_AUTH_FAILED = -25293
ERR_SEC_INTERACTION_NOT_ALLOWED = -25308
ERR_SEC_USER_CANCELED = -128
KEYCHAIN_UNLOCKED_STATUS = 1
CF_STRING_ENCODING_UTF8 = 0x08000100
# `list` returns at most this many refs (the output must stay well under the
# parent's 1 MiB limit). Past it the result says `truncated`, so a repair can
# never pass off a partial listing as the whole keychain.
LIST_LIMIT = 2000
# Test-only seam: point the macOS adapter at a throwaway keychain instead of
# the user's default. Honored only for a file named ``mbtest-*.keychain-db``
# outside ``~/Library/Keychains``; any other value refuses to run.
TEST_KEYCHAIN_ENV = "MB_CREDENTIAL_TEST_KEYCHAIN"
# Apple-signed, so its keychain identity survives Python, uv and macOS updates.
SECURITY_TOOL = "/usr/bin/security"
# `security -i` rejects input lines longer than about 4 KB; leave room for the
# command, the ref and a keychain path around the hex value.
SECURITY_HEX_LIMIT = 3600
DEFAULT_BUDGET_SECONDS = 6.0
# A move deletes the legacy item, so it starts only with time for every step
# plus cleanup. A whole move is a handful of `security` calls of well under a
# second each; this leaves several times that before the parent's deadline.
MIN_MOVE_SECONDS = 3.0
# A move keeps a full, verified copy under `<ref>.mbstage` until the final item
# verifies. Any later access finishes or undoes an interrupted move from it.
STAGE_SUFFIX = ".mbstage"
# Staged-copy state table (macOS). Stage = `<ref>.mbstage`; main = `<ref>`.
# "Gate" = only with MIN_MOVE_SECONDS left (checked again before each delete);
# without it the delete is skipped and a later access does it. Repair is a get
# with interaction allowed for a legacy read; it follows the get column.
#
# stage \ main | absent          | legacy          | sec-readable   | sec-empty      | unreadable
# absent       | get: missing    | get: read; move | get: read      | get: ready ""  | get: failure
#              | set: staged new | set: update,move| set: put       | set: put       | set: failure
#              | del: missing    | del: delete     | del: delete    | del: delete    | del: failure
# empty        | get/set: drop stage (gate; proved empty by a successful read, and
#   (proved)   |   empty values are never staged), then as the "absent" row
#              | del: delete stage, confirm gone, then main as the "absent" row
# readable     | get: finish     | get: read; move | get: drop stage| get: refill    | get: failure,
#              |   move (gate),  |   re-stages     |   (gate), main |   (gate), ready|   keep both
#              |   ready staged  |   (untrusted:   |   value        |   staged       |
#              |                 |   pending, keep)|                |                |
#              | set: as get, then write the new value (a short gate leaves the
#              |   staged copy; the readable item supersedes it on the next get)
#              | del: delete stage, confirm gone, then main; on failure leave main
# unreadable   | get: failure,   | get: read, no   | get: read      | get: failure,  | get: failure
#              |   keep (never   |   move          |                |   keep         |
#              |   missing)      | set: update     | set: put       | set: failure   | set: failure
#              | set: failure    |   in place      |                |                |
#              | del: delete the staged copy without reading it (`security` for a
#              |   security-owned copy, the framework for a legacy-owned one) and
#              |   confirm it is gone, then main as the "absent" row; fails, and
#              |   leaves main, only when the copy's owner cannot be read or the
#              |   copy is still there after the delete
#
# Invariants (one parametrized test walks every cell with each fault):
# (a) a stored value always keeps at least one durable copy;
# (b) a deleted credential never comes back;
# (c) no move or recovery delete starts without the gate;
# (d) unreadable never becomes `missing`.
# Test-only: exit at a named step of a move, to prove recovery after a crash.
# Inert unless the throwaway-keychain seam is also set.
TEST_CRASH_ENV = "MB_CREDENTIAL_TEST_CRASH_AT"


_SAFE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9:/._@+_-]{0,511}")


class _PromptPending(Exception):
    """A keychain operation would have to wait on a macOS dialog."""


class _BudgetSpent(Exception):
    """The call's time budget ended before a `security` call could start.

    Nothing was asked of the keychain, so this is not a pending dialog: it
    reports `not-checked` (#1151). A `security` call that started and then ran
    out of time is still `_PromptPending`.
    """


def _monotonic_deadline(epoch: float) -> float:
    """Turn the parent's wall-clock deadline into a monotonic one, once."""

    return time.monotonic() + (epoch - time.time())


def _failure_state(exc: BaseException) -> str:
    if isinstance(exc, _BudgetSpent):
        return "not-checked"
    return "prompt-pending" if isinstance(exc, _PromptPending) else "unavailable"


def _emit(
    state: str,
    *,
    value: str | None = None,
    migrated: bool = False,
    owner: str = "",
    refs: list[str] | None = None,
    found: int | None = None,
) -> int:
    payload: dict[str, Any] = {"state": state}
    if value is not None:
        payload["value"] = value
    if refs is not None:
        payload["refs"] = refs
    if refs is not None:
        # Every listing says how many refs it found and the cap, complete or
        # not: the parent accepts a listing as complete only when `found`
        # equals the refs it got, so a helper that predates this protocol can
        # never pass off a capped listing as the whole keychain.
        payload["found"] = found if found is not None else len(refs)
        payload["limit"] = LIST_LIMIT
        if payload["found"] > len(refs):
            payload["truncated"] = True
    if migrated:
        payload["migrated"] = True
    if owner:
        payload["owner"] = owner
    sys.stdout.write(json.dumps(payload, separators=(",", ":")))
    return 0 if state in {"ready", "missing"} else 1


def _status_state(status: int) -> str:
    if status == ERR_SEC_ITEM_NOT_FOUND:
        return "missing"
    if status == ERR_SEC_AUTH_FAILED:
        return "auth-failed"
    if status in {ERR_SEC_INTERACTION_NOT_ALLOWED, ERR_SEC_USER_CANCELED}:
        return "locked"
    return "unavailable"


def _denied_state(status: int, *, health: str) -> str:
    """Classify an item-level refusal once keychain health is known.

    With user interaction disabled, an item whose access list does not trust
    this interpreter fails at once instead of showing a dialog. On an unlocked
    keychain that refusal means a macOS prompt would be waiting for a click.
    """

    state = _status_state(status)
    if health == "ready" and state in {"auth-failed", "locked"}:
        return "prompt-pending"
    return state


def _denied_state_for(state: str, *, health: str) -> str:
    if health == "ready" and state in {"auth-failed", "locked"}:
        return "prompt-pending"
    return state


def _parse_security_password(text: str) -> str | None:
    """Decode the ``password:`` line that ``security find-generic-password -g`` writes.

    ``security`` prints a printable value in double quotes, unescaped, and
    any other value as ``0x`` followed by hex, so the two never collide.
    """

    for line in text.splitlines():
        if not line.startswith("password: "):
            continue
        rest = line[len("password: ") :]
        if rest == "":
            return ""
        if len(rest) >= 2 and rest.startswith('"') and rest.endswith('"'):
            return rest[1:-1]
        if rest.startswith("0x"):
            try:
                return bytes.fromhex(rest[2:].split(" ", 1)[0]).decode("utf-8")
            except ValueError:
                return None
        return None
    return None


def _test_keychain_path() -> str | None:
    """Return the throwaway keychain named by the test seam, if any.

    Absent means the user's keychain. Present means a throwaway keychain or
    nothing: an empty value, a wrong name, a path under ``~/Library/Keychains``,
    a symlink into it, or a hard-linked file all raise, so the seam can never
    fall through to, or alias, the login keychain.
    """

    if TEST_KEYCHAIN_ENV not in os.environ:
        return None
    raw = os.environ[TEST_KEYCHAIN_ENV]
    if not raw.strip():
        raise RuntimeError("refusing test keychain")
    path = Path(raw).expanduser().resolve()
    keychains = (Path.home() / "Library" / "Keychains").resolve()
    if (
        not path.name.startswith("mbtest-")
        or not path.name.endswith(".keychain-db")
        or path.is_relative_to(keychains)
        or not path.is_file()
        or path.stat().st_nlink != 1
    ):
        raise RuntimeError("refusing test keychain")
    return str(path)


class _MacSecurity:
    """Minimal ctypes bridge for generic-password operations."""

    shared_budget = False

    def __init__(
        self,
        *,
        interactive: bool = False,
        deadline: float | None = None,
        shared_budget: bool = False,
    ) -> None:
        # True when the parent cut this call's time short to fit a budget shared
        # by several reads: running out of it is then not a pending dialog.
        self.shared_budget = shared_budget
        # The parent sends a wall-clock deadline; it is turned into a monotonic
        # one once, here, so a clock change cannot stretch or shrink the budget.
        # The helper must finish, and stop every `security` child, before the
        # parent stops waiting for it.
        self.deadline = _monotonic_deadline(
            deadline if deadline is not None else time.time() + DEFAULT_BUDGET_SECONDS
        )
        self.migrated = False
        # What the last recovery found in the staged copy (see _recover).
        self.stage_kind = "absent"
        # Who owns the item after this call: "security", "legacy" or "".
        self.owner = ""
        self.security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        self.core = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        self.core.CFStringCreateWithCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        self.core.CFStringCreateWithCString.restype = ctypes.c_void_p
        self.core.CFDataCreate.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_long,
        ]
        self.core.CFDataCreate.restype = ctypes.c_void_p
        self.core.CFDataGetLength.argtypes = [ctypes.c_void_p]
        self.core.CFDataGetLength.restype = ctypes.c_long
        self.core.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
        self.core.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_ubyte)
        self.core.CFDictionaryCreateMutable.argtypes = [
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self.core.CFDictionaryCreateMutable.restype = ctypes.c_void_p
        self.core.CFDictionarySetValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self.core.CFRelease.argtypes = [ctypes.c_void_p]
        self.security.SecItemCopyMatching.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.security.SecItemCopyMatching.restype = ctypes.c_int32
        self.security.SecItemUpdate.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.security.SecItemUpdate.restype = ctypes.c_int32
        self.security.SecItemAdd.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.security.SecItemAdd.restype = ctypes.c_int32
        self.security.SecItemDelete.argtypes = [ctypes.c_void_p]
        self.security.SecItemDelete.restype = ctypes.c_int32
        self.security.SecKeychainCopyDefault.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        self.security.SecKeychainCopyDefault.restype = ctypes.c_int32
        self.security.SecKeychainGetStatus.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        self.security.SecKeychainGetStatus.restype = ctypes.c_int32
        self.security.SecKeychainSetUserInteractionAllowed.argtypes = [ctypes.c_bool]
        self.security.SecKeychainSetUserInteractionAllowed.restype = ctypes.c_int32
        self.security.SecKeychainOpen.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.security.SecKeychainOpen.restype = ctypes.c_int32
        self.core.CFArrayCreate.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_long,
            ctypes.c_void_p,
        ]
        self.core.CFArrayCreate.restype = ctypes.c_void_p
        self.core.CFArrayGetCount.argtypes = [ctypes.c_void_p]
        self.core.CFArrayGetCount.restype = ctypes.c_long
        self.core.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
        self.core.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
        self.security.SecKeychainItemCopyAccess.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.security.SecKeychainItemCopyAccess.restype = ctypes.c_int32
        self.security.SecAccessCopyMatchingACLList.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.security.SecAccessCopyMatchingACLList.restype = ctypes.c_void_p
        self.security.SecACLCopyContents.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_uint16),
        ]
        self.security.SecACLCopyContents.restype = ctypes.c_int32
        self.security.SecTrustedApplicationCopyData.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.security.SecTrustedApplicationCopyData.restype = ctypes.c_int32
        self.core.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.core.CFDictionaryGetValue.restype = ctypes.c_void_p
        self.core.CFGetTypeID.argtypes = [ctypes.c_void_p]
        self.core.CFGetTypeID.restype = ctypes.c_ulong
        self.core.CFStringGetTypeID.argtypes = []
        self.core.CFStringGetTypeID.restype = ctypes.c_ulong
        self.core.CFStringGetCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_long,
            ctypes.c_uint32,
        ]
        self.core.CFStringGetCString.restype = ctypes.c_bool
        if not interactive:
            # kSecUseAuthenticationUIFail does not suppress the file-keychain
            # access dialog; this does. It must run before any keychain call,
            # so an untrusted read fails at once instead of waiting on a click.
            status = int(self.security.SecKeychainSetUserInteractionAllowed(False))
            if status != ERR_SEC_SUCCESS:
                raise RuntimeError("could not disable keychain interaction")
        self.keychain: int | None = None
        self.search_list: int | None = None
        test_path = _test_keychain_path()
        self.keychain_path = test_path
        if test_path is not None:
            keychain = ctypes.c_void_p()
            status = int(
                self.security.SecKeychainOpen(test_path.encode("utf-8"), ctypes.byref(keychain))
            )
            if status != ERR_SEC_SUCCESS or not keychain.value:
                raise RuntimeError("could not open test keychain")
            self.keychain = int(keychain.value)
            items = (ctypes.c_void_p * 1)(self.keychain)
            search_list = self.core.CFArrayCreate(None, items, 1, None)
            if not search_list:
                raise RuntimeError("could not allocate search list")
            self.search_list = int(search_list)

    @staticmethod
    def _constant(library: Any, name: str) -> int:
        value = ctypes.c_void_p.in_dll(library, name).value
        if value is None:
            raise RuntimeError("missing framework constant")
        return value

    def _string(self, value: str) -> int:
        result = self.core.CFStringCreateWithCString(
            None,
            value.encode("utf-8"),
            CF_STRING_ENCODING_UTF8,
        )
        if not result:
            raise RuntimeError("could not allocate string")
        return int(result)

    def _data(self, value: str) -> int:
        raw = value.encode("utf-8")
        buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        result = self.core.CFDataCreate(None, buffer, len(raw))
        if not result:
            raise RuntimeError("could not allocate data")
        return int(result)

    def _dictionary(self, pairs: list[tuple[int, int]]) -> int:
        # Null callbacks are intentional: every key/value remains alive for
        # the duration of the synchronous Security.framework call.
        result = self.core.CFDictionaryCreateMutable(None, 0, None, None)
        if not result:
            raise RuntimeError("could not allocate dictionary")
        for key, value in pairs:
            self.core.CFDictionarySetValue(result, key, value)
        return int(result)

    def _query(
        self, ref: str, *, return_data: bool = False, return_ref: bool = False
    ) -> tuple[int, list[int]]:
        service = self._string(SERVICE_NAME)
        account = self._string(ref)
        owned = [service, account]
        pairs = [
            (
                self._constant(self.security, "kSecClass"),
                self._constant(self.security, "kSecClassGenericPassword"),
            ),
            (self._constant(self.security, "kSecAttrService"), service),
            (self._constant(self.security, "kSecAttrAccount"), account),
            (
                self._constant(self.security, "kSecUseAuthenticationUI"),
                self._constant(self.security, "kSecUseAuthenticationUIFail"),
            ),
        ]
        if self.search_list is not None:
            pairs.append((self._constant(self.security, "kSecMatchSearchList"), self.search_list))
        if return_data or return_ref:
            pairs.extend(
                [
                    (
                        self._constant(self.security, "kSecMatchLimit"),
                        self._constant(self.security, "kSecMatchLimitOne"),
                    ),
                    (
                        self._constant(
                            self.security, "kSecReturnData" if return_data else "kSecReturnRef"
                        ),
                        self._constant(self.core, "kCFBooleanTrue"),
                    ),
                ]
            )
        return self._dictionary(pairs), owned

    def _release_all(self, values: list[int]) -> None:
        for value in values:
            self.core.CFRelease(value)

    # -- Legacy items: created by a Python interpreter through SecItem ------

    def _ctypes_get(self, ref: str, *, health: str) -> tuple[str, str | None]:
        query, owned = self._query(ref, return_data=True)
        result = ctypes.c_void_p()
        try:
            status = int(self.security.SecItemCopyMatching(query, ctypes.byref(result)))
            if status != ERR_SEC_SUCCESS:
                return _denied_state(status, health=health), None
            if not result.value:
                return "unavailable", None
            length = int(self.core.CFDataGetLength(result.value))
            pointer = self.core.CFDataGetBytePtr(result.value)
            raw = ctypes.string_at(pointer, length)
            return "ready", raw.decode("utf-8")
        finally:
            if result.value:
                self.core.CFRelease(result.value)
            self.core.CFRelease(query)
            self._release_all(owned)

    def _update(self, ref: str, value: str) -> int:
        query, query_owned = self._query(ref)
        data = self._data(value)
        update = self._dictionary([(self._constant(self.security, "kSecValueData"), data)])
        try:
            return int(self.security.SecItemUpdate(query, update))
        finally:
            self.core.CFRelease(update)
            self.core.CFRelease(query)
            self._release_all(query_owned)
            self.core.CFRelease(data)

    def _ctypes_add(self, ref: str, value: str) -> int:
        service = self._string(SERVICE_NAME)
        account = self._string(ref)
        data = self._data(value)
        pairs = [
            (
                self._constant(self.security, "kSecClass"),
                self._constant(self.security, "kSecClassGenericPassword"),
            ),
            (self._constant(self.security, "kSecAttrService"), service),
            (self._constant(self.security, "kSecAttrAccount"), account),
            (self._constant(self.security, "kSecValueData"), data),
            (
                self._constant(self.security, "kSecUseAuthenticationUI"),
                self._constant(self.security, "kSecUseAuthenticationUIFail"),
            ),
        ]
        if self.keychain is not None:
            pairs.append((self._constant(self.security, "kSecUseKeychain"), self.keychain))
        add = self._dictionary(pairs)
        try:
            return int(self.security.SecItemAdd(add, None))
        finally:
            self.core.CFRelease(add)
            self._release_all([service, account, data])

    def _ctypes_delete(self, ref: str) -> int:
        query, owned = self._query(ref)
        try:
            return int(self.security.SecItemDelete(query))
        finally:
            self.core.CFRelease(query)
            self._release_all(owned)

    # -- Which code an item trusts (non-secret, never prompts) --------------

    def _item_owner(self, ref: str) -> str:
        """Return ``security``, ``legacy`` or ``absent`` for one item, or a failure state.

        Reads the item's access list, never its data, so it cannot prompt. An
        item counts as ``security`` only when ``/usr/bin/security`` is the
        first application its decrypt rule trusts, which is how macOS records
        the creating tool. Only those items are ever read through ``security``:
        it has no way to refuse a dialog, so any other item could block on one.
        """

        query, owned = self._query(ref, return_ref=True)
        item = ctypes.c_void_p()
        access = ctypes.c_void_p()
        acls: int | None = None
        apps = ctypes.c_void_p()
        description = ctypes.c_void_p()
        try:
            status = int(self.security.SecItemCopyMatching(query, ctypes.byref(item)))
            if status == ERR_SEC_ITEM_NOT_FOUND:
                return "absent"
            if status != ERR_SEC_SUCCESS or not item.value:
                return _status_state(status) if status != ERR_SEC_SUCCESS else "unavailable"
            status = int(self.security.SecKeychainItemCopyAccess(item, ctypes.byref(access)))
            if status != ERR_SEC_SUCCESS or not access.value:
                return "legacy"
            acls = self.security.SecAccessCopyMatchingACLList(
                access, self._constant(self.security, "kSecACLAuthorizationDecrypt")
            )
            if not acls or int(self.core.CFArrayGetCount(acls)) < 1:
                return "legacy"
            acl = self.core.CFArrayGetValueAtIndex(acls, 0)
            selector = ctypes.c_uint16()
            status = int(
                self.security.SecACLCopyContents(
                    acl, ctypes.byref(apps), ctypes.byref(description), ctypes.byref(selector)
                )
            )
            if status != ERR_SEC_SUCCESS or not apps.value:
                # No application list means any application; still not proof
                # that `security` can read it without a partition prompt.
                return "legacy"
            if int(self.core.CFArrayGetCount(apps.value)) < 1:
                return "legacy"
            first = self.core.CFArrayGetValueAtIndex(apps.value, 0)
            data = ctypes.c_void_p()
            status = int(self.security.SecTrustedApplicationCopyData(first, ctypes.byref(data)))
            if status != ERR_SEC_SUCCESS or not data.value:
                return "legacy"
            try:
                length = int(self.core.CFDataGetLength(data.value))
                path = ctypes.string_at(self.core.CFDataGetBytePtr(data.value), length)
            finally:
                self.core.CFRelease(data.value)
            return "security" if path.rstrip(b"\0") == SECURITY_TOOL.encode() else "legacy"
        finally:
            for value in (description.value, apps.value, acls, access.value, item.value):
                if value:
                    self.core.CFRelease(value)
            self.core.CFRelease(query)
            self._release_all(owned)

    # -- Every mb item, by attributes only (non-secret, never prompts) --------

    def _ctypes_accounts(self) -> tuple[str, list[str]]:
        """Return the account of every item under the ``mainbranch`` service.

        Asks for attributes only (``kSecReturnAttributes``), never data, so
        macOS decrypts nothing and has no reason to ask; interaction is off as
        well, so a refusal fails instead of showing a dialog.
        """

        service = self._string(SERVICE_NAME)
        pairs = [
            (
                self._constant(self.security, "kSecClass"),
                self._constant(self.security, "kSecClassGenericPassword"),
            ),
            (self._constant(self.security, "kSecAttrService"), service),
            (
                self._constant(self.security, "kSecMatchLimit"),
                self._constant(self.security, "kSecMatchLimitAll"),
            ),
            (
                self._constant(self.security, "kSecReturnAttributes"),
                self._constant(self.core, "kCFBooleanTrue"),
            ),
            (
                self._constant(self.security, "kSecUseAuthenticationUI"),
                self._constant(self.security, "kSecUseAuthenticationUIFail"),
            ),
        ]
        if self.search_list is not None:
            pairs.append((self._constant(self.security, "kSecMatchSearchList"), self.search_list))
        query = self._dictionary(pairs)
        result = ctypes.c_void_p()
        try:
            status = int(self.security.SecItemCopyMatching(query, ctypes.byref(result)))
            if status == ERR_SEC_ITEM_NOT_FOUND:
                return "ready", []
            if status != ERR_SEC_SUCCESS or not result.value:
                return _status_state(status) if status != ERR_SEC_SUCCESS else "unavailable", []
            account_key = self._constant(self.security, "kSecAttrAccount")
            string_type = int(self.core.CFStringGetTypeID())
            accounts: list[str] = []
            for index in range(int(self.core.CFArrayGetCount(result.value))):
                attributes = self.core.CFArrayGetValueAtIndex(result.value, index)
                account = self.core.CFDictionaryGetValue(attributes, account_key)
                if not account or int(self.core.CFGetTypeID(account)) != string_type:
                    continue
                buffer = ctypes.create_string_buffer(2048)
                if self.core.CFStringGetCString(
                    account, buffer, len(buffer), CF_STRING_ENCODING_UTF8
                ):
                    accounts.append(buffer.value.decode("utf-8"))
            return "ready", accounts
        finally:
            if result.value:
                self.core.CFRelease(result.value)
            self.core.CFRelease(query)
            self.core.CFRelease(service)

    def list_refs(self) -> tuple[str, list[str], int]:
        """Every mb ref in the keychain, staged copies included, sorted.

        Refs that mb could not have written (see ``_SAFE_REF``) are left out.
        At most ``LIST_LIMIT`` refs are returned, with the number found, so a
        caller can tell a cut listing from a complete one.
        """

        health = self.health()
        if health != "ready":
            return health, [], 0
        state, accounts = self._ctypes_accounts()
        if state != "ready":
            return _denied_state_for(state, health=health), [], 0
        refs = sorted({account for account in accounts if _SAFE_REF.fullmatch(account)})
        return "ready", refs[:LIST_LIMIT], len(refs)

    # -- Items created by Apple-signed /usr/bin/security ---------------------

    def _security_tool(self, args: list[str], *, stdin: str | None = None) -> Any:
        """Run ``/usr/bin/security`` within the remaining budget.

        ``security`` cannot be told to fail instead of showing a dialog, so the
        caller must already have proved the item trusts it; this deadline is
        the last guard, and expiry reports a pending prompt.
        """

        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise _BudgetSpent
        try:
            if stdin is None:
                return subprocess.run(
                    [SECURITY_TOOL, *args],
                    check=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=remaining,
                )
            return subprocess.run(
                [SECURITY_TOOL, *args],
                check=False,
                input=stdin,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=remaining,
            )
        except subprocess.TimeoutExpired as exc:
            if self.shared_budget:
                raise _BudgetSpent from exc
            raise _PromptPending from exc

    def _keychain_args(self) -> list[str]:
        return [self.keychain_path] if self.keychain_path is not None else []

    def _security_get(self, ref: str) -> tuple[str, str | None]:
        completed = self._security_tool(
            ["find-generic-password", "-s", SERVICE_NAME, "-a", ref, "-g", *self._keychain_args()]
        )
        if completed.returncode != 0:
            return ("missing" if completed.returncode == 44 else "unavailable"), None
        value = _parse_security_password(completed.stderr or "")
        if value is None:
            return "unavailable", None
        return "ready", value

    def _security_put(self, ref: str, value: str, *, exists: bool) -> str:
        """Write ``value`` so that ``/usr/bin/security`` owns the item.

        The value goes over stdin as hex (``security -i``), never in argv. A
        value too long for one ``security -i`` line is written as an empty
        item by ``security`` and then filled in through the Security
        framework, which leaves the item's access list unchanged. If that fill
        fails, the empty item is removed again.
        """

        encoded = value.encode("utf-8").hex()
        fits = len(encoded) <= SECURITY_HEX_LIMIT
        keychain = f' "{self.keychain_path}"' if self.keychain_path is not None else ""
        if exists and not fits:
            status = self._update(ref, value)
            return "ready" if status == ERR_SEC_SUCCESS else _status_state(status)
        flag = "-U " if exists else ""
        hex_value = encoded if fits else ""
        command = (
            f'add-generic-password {flag}-s {SERVICE_NAME} -a "{ref}" -X "{hex_value}"{keychain}\n'
        )
        completed = self._security_tool(["-i"], stdin=command)
        if completed.returncode != 0 or "returned -" in (completed.stderr or ""):
            return "unavailable"
        if not fits:
            self._crash_point("after-placeholder")
            status = self._update(ref, value)
            if status != ERR_SEC_SUCCESS:
                with contextlib.suppress(Exception):
                    self._security_delete(ref)
                return _status_state(status)
        return "ready"

    def _security_delete(self, ref: str) -> str:
        completed = self._security_tool(
            ["delete-generic-password", "-s", SERVICE_NAME, "-a", ref, *self._keychain_args()]
        )
        if completed.returncode == 0:
            return "ready"
        return "missing" if completed.returncode == 44 else "unavailable"

    def _verified(self, ref: str, value: str) -> bool:
        if self._item_owner(ref) != "security":
            return False
        state, stored = self._security_get(ref)
        return state == "ready" and stored == value

    def _can_move(self) -> bool:
        return self.deadline - time.monotonic() >= MIN_MOVE_SECONDS

    def _crash_point(self, step: str) -> None:
        if self.keychain_path is not None and os.environ.get(TEST_CRASH_ENV) == step:
            os._exit(70)

    def _put_verified(self, ref: str, value: str) -> bool:
        exists = self._item_owner(ref) == "security"
        return self._security_put(ref, value, exists=exists) == "ready" and self._verified(
            ref, value
        )

    def _staged_write(self, ref: str, value: str, *, replaces_legacy: bool) -> bool:
        """Make ``ref`` a ``security``-owned item holding ``value``; never lose it.

        1. Write the full value to ``<ref>.mbstage`` and verify it.
        2. Delete the legacy item (when moving one).
        3. Write the final item and verify it.
        4. Delete the staged copy.

        A crash at any point leaves either the legacy item or a verified staged
        copy, and the next access recovers from it. On an ordinary failure the
        legacy item is put back and the staged copy is kept.
        """

        if value == "" or not self._can_move():
            # An empty value is never staged, so an empty staged copy always
            # means an interrupted fill and is safe to drop (see _recover).
            return False
        stage = ref + STAGE_SUFFIX
        try:
            if not self._put_verified(stage, value):
                with contextlib.suppress(Exception):
                    if self._item_owner(stage) == "security":
                        self._security_delete(stage)
                return False
        except Exception:
            return False
        self._crash_point("after-stage")
        if not self._can_move():
            # Too little time left to finish: keep the legacy item. The staged
            # copy is redundant and is refreshed by the next move.
            return False
        if replaces_legacy and self._ctypes_delete(ref) != ERR_SEC_SUCCESS:
            # The legacy item stays where it is, so the staged copy is redundant.
            with contextlib.suppress(Exception):
                self._security_delete(stage)
            return False
        self._crash_point("after-legacy-delete")
        try:
            done = self._put_verified(ref, value)
        except Exception:
            done = False
        self._crash_point("after-final")
        if done:
            with contextlib.suppress(Exception):
                self._security_delete(stage)
            return True
        # Put a copy back where this Python can read it, and keep the staged
        # copy as the backup until a later access finishes the move.
        with contextlib.suppress(Exception):
            if self._item_owner(ref) == "security":
                self._security_delete(ref)
        if self._ctypes_add(ref, value) != ERR_SEC_SUCCESS:
            self._update(ref, value)
        return False

    def _stage_state(self, stage: str) -> tuple[str, str | None, str]:
        """Classify a staged copy: ``(kind, value, failure state)``.

        ``kind`` is ``absent``, ``empty`` (read successfully, holds ""),
        ``readable`` or ``unreadable``. Only a successful read can make a
        staged copy ``empty``; any failure is ``unreadable`` and keeps it.
        """

        try:
            owner = self._item_owner(stage)
            if owner == "absent":
                return "absent", None, ""
            if owner != "security":
                # Not one this code made, or its owner could not be read.
                return "unreadable", None, owner if owner != "legacy" else "unavailable"
            state, value = self._security_get(stage)
        except Exception as exc:
            return "unreadable", None, _failure_state(exc)
        if state != "ready" or value is None:
            return "unreadable", None, state if state != "missing" else "unavailable"
        return ("empty" if value == "" else "readable"), value, ""

    def _main_state(self, ref: str) -> tuple[str, str | None, str]:
        """Classify the item itself without reading a legacy item's data.

        ``absent``, ``legacy``, ``security-readable``, ``security-empty`` or
        ``unreadable`` (with its failure state).
        """

        try:
            owner = self._item_owner(ref)
            if owner in {"absent", "legacy"}:
                return owner, None, ""
            if owner != "security":
                return "unreadable", None, owner
            state, value = self._security_get(ref)
        except Exception as exc:
            return "unreadable", None, _failure_state(exc)
        if state == "missing":
            return "absent", None, ""
        if state != "ready" or value is None:
            return "unreadable", None, state
        return ("security-empty" if value == "" else "security-readable"), value, ""

    def _drop_stage(self, stage: str) -> None:
        """Remove a staged copy that is proved redundant, if time allows."""

        if self._can_move():
            with contextlib.suppress(Exception):
                self._security_delete(stage)

    def _recover(self, ref: str) -> tuple[str, str | None] | None:
        """Finish or undo a move that a crash or timeout interrupted.

        Returns a result for this access, or None when the item itself should
        be read as usual. Invariants: a stored value always keeps at least one
        durable copy; an unreadable staged copy is never deleted and never
        turns into ``missing``; nothing is deleted without the time gate.
        The full table of cases is at the top of this module.
        """

        stage = ref + STAGE_SUFFIX
        kind, staged, stage_failure = self._stage_state(stage)
        self.stage_kind = kind
        if kind == "absent":
            return None
        if kind == "empty":
            # Proved empty by a successful read. Empty values are never
            # staged, so this is an interrupted fill of the staged copy:
            # nothing was deleted yet and the item still holds the value.
            self._drop_stage(stage)
            return None
        main, value, main_failure = self._main_state(ref)
        if main == "unreadable":
            return main_failure, None
        if kind == "unreadable":
            if main in {"absent", "security-empty"}:
                # The value may live only in the staged copy: report the
                # failure for this access and keep everything.
                return stage_failure, None
            # The item holds the value; read it as usual (without moving it).
            return None
        if main in {"absent", "security-empty"}:
            # Interrupted after the legacy delete, or while filling the final
            # item: finish the move from the staged copy.
            if self._can_move():
                try:
                    done = self._put_verified(ref, staged or "")
                except Exception:
                    done = False
                if done:
                    self.migrated = True
                    self.owner = "security"
                    self._drop_stage(stage)
            return "ready", staged
        if main == "security-readable":
            # The final item verified (or a newer write replaced it).
            self._drop_stage(stage)
            self.owner = "security"
            return "ready", value
        # A legacy item is still there (put back after a failure, or the crash
        # came before it was deleted): read it as usual; a move re-stages.
        return None

    def _remove_stage(self, stage: str) -> str | None:
        """Delete a staged copy for ``delete``; None once it is confirmed gone."""

        try:
            owner = self._item_owner(stage)
            if owner == "absent":
                return None
            if owner == "security":
                state = self._security_delete(stage)
            elif owner == "legacy":
                status = self._ctypes_delete(stage)
                state = (
                    "ready"
                    if status in {ERR_SEC_SUCCESS, ERR_SEC_ITEM_NOT_FOUND}
                    else (_status_state(status))
                )
            else:
                return owner
            if state not in {"ready", "missing"}:
                return state
            return None if self._item_owner(stage) == "absent" else "unavailable"
        except Exception as exc:
            return _failure_state(exc)

    # -- Public operations ---------------------------------------------------

    def get(self, ref: str) -> tuple[str, str | None]:
        health = self.health()
        if health != "ready":
            # A locked keychain would need an unlock dialog: fail fast.
            return health, None
        recovered = self._recover(ref)
        if recovered is not None:
            return recovered
        owner = self._item_owner(ref)
        if owner == "absent":
            return "missing", None
        if owner == "security":
            self.owner = "security"
            return self._security_get(ref)
        if owner != "legacy":
            return _denied_state_for(owner, health=health), None
        state, value = self._ctypes_get(ref, health=health)
        self.owner = "legacy"
        if state == "ready" and value is not None and self.stage_kind != "unreadable":
            # Without enough time left for the whole move, read only and move
            # next time: a delete must never be cut short by the parent.
            self.migrated = self._staged_write(ref, value, replaces_legacy=True)
            if self.migrated:
                self.owner = "security"
        return state, value

    def set(self, ref: str, value: str) -> str:
        health = self.health()
        if health != "ready":
            return health
        recovered = self._recover(ref)
        if recovered is not None and recovered[0] != "ready":
            # The item or its staged copy cannot be read now: write nothing.
            return recovered[0]
        owner = self._item_owner(ref)
        if owner == "security":
            return self._security_put(ref, value, exists=True)
        if owner == "legacy":
            # Replace the value in place first, so a failure never loses the
            # previous credential, then move the item exactly as a read would.
            # If this Python may not remove the old item, it stays legacy and a
            # later read reports the pending prompt for the keychain repair.
            status = self._update(ref, value)
            if status != ERR_SEC_SUCCESS:
                return _denied_state(status, health=health)
            if self.stage_kind != "unreadable":
                self._staged_write(ref, value, replaces_legacy=True)
            return "ready"
        if owner != "absent":
            return _denied_state_for(owner, health=health)
        if self._staged_write(ref, value, replaces_legacy=False):
            return "ready"
        # Never leave a write undone: fall back to the legacy store. A staged
        # copy, if one was kept, holds the same value and is cleaned up later.
        status = self._ctypes_add(ref, value)
        if status == ERR_SEC_DUPLICATE_ITEM:
            status = self._update(ref, value)
        return "ready" if status == ERR_SEC_SUCCESS else _denied_state(status, health=health)

    def delete(self, ref: str) -> str:
        health = self.health()
        if health != "ready":
            return health
        # The staged copy goes first and must be confirmed gone: otherwise the
        # next access would restore the credential from it.
        failure = self._remove_stage(ref + STAGE_SUFFIX)
        if failure is not None:
            return failure
        owner = self._item_owner(ref)
        if owner == "absent":
            return "missing"
        if owner == "security":
            return self._security_delete(ref)
        status = self._ctypes_delete(ref)
        return "ready" if status == ERR_SEC_SUCCESS else _denied_state(status, health=health)

    def health(self) -> str:
        flags = ctypes.c_uint32()
        if self.keychain is not None:
            status = int(self.security.SecKeychainGetStatus(self.keychain, ctypes.byref(flags)))
        else:
            keychain = ctypes.c_void_p()
            status = int(self.security.SecKeychainCopyDefault(ctypes.byref(keychain)))
            if status != ERR_SEC_SUCCESS:
                return _status_state(status)
            try:
                status = int(self.security.SecKeychainGetStatus(keychain, ctypes.byref(flags)))
            finally:
                if keychain.value:
                    self.core.CFRelease(keychain.value)
        if status != ERR_SEC_SUCCESS:
            return _status_state(status)
        return "ready" if flags.value & KEYCHAIN_UNLOCKED_STATUS else "locked"


def _macos(action: str, payload: dict[str, Any]) -> tuple[str, str | None, bool, str]:
    if platform.system() != "Darwin":
        return "unavailable", None, False, ""
    deadline = payload.get("deadline_epoch")
    adapter = _MacSecurity(
        interactive=payload.get("interactive") is True,
        deadline=float(deadline) if isinstance(deadline, (int, float)) else None,
        shared_budget=payload.get("shared_budget") is True,
    )
    ref = str(payload.get("ref") or "")
    if action == "health":
        return adapter.health(), None, False, ""
    if not ref or not _SAFE_REF.fullmatch(ref) or ref.endswith(STAGE_SUFFIX):
        # Refs are generated by mb; anything else could break `security -i`
        # quoting or address a staged copy directly.
        return "unavailable", None, False, ""
    try:
        if action == "get":
            state, value = adapter.get(ref)
            return state, value, adapter.migrated, adapter.owner if state == "ready" else ""
        if action == "set":
            value = payload.get("value")
            if not isinstance(value, str):
                return "unavailable", None, False, ""
            return adapter.set(ref, value), None, False, ""
        if action == "delete":
            return adapter.delete(ref), None, False, ""
    except _PromptPending:
        return "prompt-pending", None, False, ""
    except _BudgetSpent:
        return "not-checked", None, False, ""
    return "unavailable", None, False, ""


def _macos_list(payload: dict[str, Any]) -> tuple[str, list[str], int]:
    """List mb's keychain refs. Always with interaction off, whatever the payload says."""

    if platform.system() != "Darwin":
        return "unavailable", [], 0
    deadline = payload.get("deadline_epoch")
    adapter = _MacSecurity(
        interactive=False,
        deadline=float(deadline) if isinstance(deadline, (int, float)) else None,
    )
    return adapter.list_refs()


def _secret_service_items(collection: Any, ref: str) -> list[Any]:
    return list(collection.search_items({"service": SERVICE_NAME, "username": ref}))


def _secret_service_item(items: list[Any]) -> Any | None:
    """Choose one compatible item without depending on service search order."""

    if not items:
        return None
    if len(items) == 1:
        return items[0]
    by_application: dict[str, list[Any]] = {}
    for item in items:
        attributes = item.get_attributes()
        application = str(attributes.get("application") or "")
        by_application.setdefault(application, []).append(item)
    for application in ("mainbranch", "Python keyring library"):
        matches = by_application.get(application, [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError("ambiguous credential items")
    raise RuntimeError("ambiguous credential items")


def _secret_service_state(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    if "locked" in name or "prompt" in name or "cancel" in name:
        return "locked"
    return "unavailable"


def _secret_service(action: str, payload: dict[str, Any]) -> tuple[str, str | None]:
    if platform.system() != "Linux":
        return "unavailable", None
    module = importlib.import_module("secretstorage")
    connection = module.dbus_init()
    collection = module.get_collection_by_alias(connection, "default")
    if collection is None:
        return "unavailable", None
    if collection.is_locked():
        return "locked", None
    if action == "health":
        return "ready", None
    ref = str(payload.get("ref") or "")
    if not ref:
        return "unavailable", None
    items = _secret_service_items(collection, ref)
    if any(item.is_locked() for item in items):
        return "locked", None
    item = _secret_service_item(items)
    if action == "get":
        if item is None:
            return "missing", None
        secret = item.get_secret()
        return "ready", bytes(secret).decode("utf-8")
    if action == "set":
        value = payload.get("value")
        if not isinstance(value, str):
            return "unavailable", None
        if item is not None:
            # Update the matched item in place. In particular, preserve the
            # attributes on legacy Python keyring items instead of creating a
            # second record whose application attribute differs.
            item.set_secret(value.encode("utf-8"))
            return "ready", None
        collection.create_item(
            f"Main Branch credential ({ref})",
            {
                "application": "mainbranch",
                "service": SERVICE_NAME,
                "username": ref,
            },
            value.encode("utf-8"),
            replace=True,
        )
        return "ready", None
    if action == "delete":
        for item in items:
            item.delete()
        return ("ready" if items else "missing"), None
    return "unavailable", None


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.read(1_048_577)
    if len(raw) > 1_048_576:
        raise ValueError("payload too large")
    value = json.loads(raw or "{}")
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    return value


def main() -> int:
    if len(sys.argv) != 3:
        return _emit("unavailable")
    backend, action = sys.argv[1:]
    if action not in {"get", "set", "delete", "health", "list"}:
        return _emit("unavailable")
    try:
        payload = _read_payload()
        migrated, owner = False, ""
        if action == "list":
            # Only the macOS Keychain can be enumerated without reading values.
            state, refs, found = (
                _macos_list(payload) if backend == "macos-keychain" else ("unavailable", [], 0)
            )
            if state != "ready":
                return _emit(state)
            return _emit(state, refs=refs, found=found)
        if backend == "macos-keychain":
            state, value, migrated, owner = _macos(action, payload)
        elif backend == "secret-service":
            state, value = _secret_service(action, payload)
        else:
            state, value = "unavailable", None
    except BaseException as exc:
        state, value, migrated, owner = _secret_service_state(exc), None, False, ""
    return _emit(state, value=value, migrated=migrated, owner=owner)


if __name__ == "__main__":
    raise SystemExit(main())
