"""Encrypted multi-account shop state, independent of match subscriptions.

Single process only. Notification claims are saved before sending: an ambiguous
Discord failure may skip a delivery, but restarting never replays that claim.
"""

import asyncio
import time
import uuid

import aiosqlite

from valorant.shop_service import (
    ShopService,
    ShopError,
    LoginExpired,
    account_label,
    parse_callback,
)


class MultiShopService(ShopService):
    def __init__(self, vault, client, allowed):
        super().__init__(vault, client, allowed)
        self.owner_locks = {}
        self.requests = asyncio.Semaphore(3)

    def owner_lock(self, owner):
        return self.owner_locks.setdefault(owner, asyncio.Lock())

    async def _load(self, owner):
        value = await self.vault.get(owner)
        if value is None:
            return {"version": 2, "accounts": {}, "notify": False, "states": {}}
        if value.get("version") == 2:
            return value
        if "puuid" not in value:
            raise ShopError("Stored account needs attention. Contact the bot owner.")
        data = {
            "version": 2,
            "accounts": {value["puuid"]: value},
            "notify": False,
            "states": {},
        }
        await self.vault.put(owner, data)
        return data

    async def accounts(self, owner):
        self.check(owner)
        async with self.owner_lock(owner):
            data = await self._load(owner)
            return [
                dict(id=p, label=account_label(a), expired=bool(a.get("auth_required")))
                for p, a in data["accounts"].items()
            ], data["notify"]

    async def linked_account(self, owner):
        accounts, _ = await self.accounts(owner)
        return ", ".join(a["label"] for a in accounts) or None

    async def login(self, owner, attempt, callback):
        self.check(owner)
        async with self.owner_lock(owner):
            pending = self.pending.get(owner)
            if not pending or pending[0] != attempt or pending[2] < time.monotonic():
                raise ShopError(
                    "Login request expired or was replaced. Start /login again."
                )
            code = parse_callback(callback)
            del self.pending[owner]
            account = await self.client.login(code, pending[1])
            puuid = str(uuid.UUID(account["puuid"]))
            data = await self._load(owner)
            if puuid not in data["accounts"] and len(data["accounts"]) >= 25:
                raise ShopError(
                    "Up to 25 shop accounts are supported. Remove one first."
                )
            data["accounts"][puuid] = account
            # Preserve the current round on reauthorization; clear the one-off warning.
            state = data["states"].setdefault(puuid, {})
            state.pop("warned", None)
            state.pop("retry", None)
            await self.vault.put(owner, data)
            self.cache.pop((owner, puuid), None)
            return account_label(account)

    def _select(self, data, account):
        if account in data["accounts"]:
            return account
        matches = [
            p
            for p, a in data["accounts"].items()
            if account_label(a).casefold() == account.casefold()
        ]
        if len(matches) != 1:
            raise ShopError("Select one of your linked accounts using /accounts.")
        return matches[0]

    async def logout(self, owner, account):
        self.check(owner)
        async with self.owner_lock(owner):
            data = await self._load(owner)
            puuid = self._select(data, account)
            del data["accounts"][puuid]
            data["states"].pop(puuid, None)
            self.cache.pop((owner, puuid), None)
            self.pending.pop(owner, None)
            if not data["accounts"]:
                data["notify"] = False
            await self.vault.put(owner, data)

    async def _shop(self, owner, data, puuid):
        async with self.requests:
            return await self._fetch_shop(owner, data, puuid)

    async def _fetch_shop(self, owner, data, puuid):
        account = data["accounts"][puuid]
        if account.get("auth_required"):
            raise LoginExpired("This account needs /login again.")
        cached = self.cache.get((owner, puuid))
        if cached and min(cached["expires"], cached["fetched_at"] + 300) > time.time():
            return cached
        try:
            if account["expires"] <= time.time() + 120:
                account = await self.client.refresh(account)
                data["accounts"][puuid] = account
                await self.vault.put(owner, data)
            result = await self.client.shop(account)
        except LoginExpired:
            # Keep only identity metadata, never keep rejected credentials.
            data["accounts"][puuid] = {
                k: account[k]
                for k in ("puuid", "name", "tag", "region")
                if k in account
            }
            data["accounts"][puuid]["auth_required"] = True
            self.cache.pop((owner, puuid), None)
            await self.vault.put(owner, data)
            raise
        if not account.get("tag"):
            try:
                account = await self.client.identity(account)
                data["accounts"][puuid] = account
                await self.vault.put(owner, data)
            except Exception:
                pass
        result["riot_id"] = account_label(account)
        result["fetched_at"] = time.time()
        for item in result["offers"]:
            try:
                item.update(await self.client.skin(item["id"]))
            except Exception:
                item.update(name="Skin " + item["id"], icon=None)
        if len(self.cache) >= 100:
            self.cache.pop(next(iter(self.cache)))
        self.cache[(owner, puuid)] = result
        return result

    async def shop(self, owner, account):
        self.check(owner)
        async with self.owner_lock(owner):
            data = await self._load(owner)
            return await self._shop(owner, data, self._select(data, account))

    async def set_notifications(self, owner, enabled):
        self.check(owner)
        async with self.owner_lock(owner):
            data = await self._load(owner)
            if enabled and not data["accounts"]:
                raise ShopError("Use /login to add an account first.")
            if enabled and not data["notify"]:
                # Do not backfill today's store, including after off/on.
                data["states"] = {}
            data["notify"] = enabled
            await self.vault.put(owner, data)

    async def owners(self):
        async with aiosqlite.connect(self.vault.path) as db:
            async with db.execute("SELECT owner FROM credentials") as cursor:
                return [int(row[0]) for row in await cursor.fetchall()]

    async def notify_owner(self, owner, send):
        self.check(owner)
        async with self.owner_lock(owner):
            data = await self._load(owner)
            if not data["notify"]:
                return
            stores, warnings = [], []
            deadline = time.monotonic() + 120
            for puuid in list(data["accounts"]):
                if time.monotonic() >= deadline:
                    break
                state = data["states"].setdefault(puuid, {})
                now = time.time()
                if state.get("retry", 0) > now:
                    continue
                if data["accounts"][puuid].get("auth_required"):
                    if not state.get("warned"):
                        warnings.append(account_label(data["accounts"][puuid]))
                        state["warned"] = True
                    continue
                if state.get("next", 0) > now:
                    continue
                try:
                    async with asyncio.timeout(
                        min(60, max(1, deadline - time.monotonic()))
                    ):
                        result = await self._shop(owner, data, puuid)
                    expiry = float(result["expires"])
                    if expiry <= now + 30:
                        state["retry"] = now + 120
                        continue
                    previous = state.get("next")
                    if previous and expiry > previous + 60:
                        stores.append(result)
                    state["next"] = expiry + 15
                    state.pop("retry", None)
                except LoginExpired:
                    if not state.get("warned"):
                        warnings.append(account_label(data["accounts"][puuid]))
                        state["warned"] = True
                except Exception:
                    state["retry"] = now + 300
            # Durable at-most-once claim. No credentials or response bodies enter DMs.
            await self.vault.put(owner, data)
            if stores or warnings:
                async with asyncio.timeout(60):
                    delivered = await send(owner, stores, warnings)
                if not delivered:
                    data["notify"] = False
                    await self.vault.put(owner, data)
