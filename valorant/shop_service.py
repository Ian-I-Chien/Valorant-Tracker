"""Opt-in experimental store access, independent of Henrik and subscriptions.

Only one bot process may own a vault. Credential-bearing responses must never
be logged. The Riot client flow is unofficial and may stop working at any time.
"""

import asyncio
import base64
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import aiohttp
import aiosqlite
from cryptography.fernet import Fernet, InvalidToken


class ShopError(Exception):
    """Only fixed, non-sensitive messages may be used here."""


class LoginExpired(ShopError):
    pass


class Vault:
    def __init__(self, path, key):
        self.path = Path(path)
        self.cipher = Fernet(key)

    async def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Create privately before SQLite opens it; never change a shared parent.
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA secure_delete=ON")
            await db.execute(
                "CREATE TABLE IF NOT EXISTS credentials "
                "(owner TEXT PRIMARY KEY, encrypted BLOB NOT NULL)"
            )
            await db.commit()

    async def get(self, owner):
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT encrypted FROM credentials WHERE owner=?", (str(owner),)
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        try:
            return json.loads(self.cipher.decrypt(row[0]))
        except (InvalidToken, ValueError):
            raise ShopError(
                "Cannot decrypt shop credentials. Contact the bot owner."
            ) from None

    async def put(self, owner, value):
        encrypted = self.cipher.encrypt(json.dumps(value).encode())
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO credentials VALUES (?, ?) ON CONFLICT(owner) "
                "DO UPDATE SET encrypted=excluded.encrypted",
                (str(owner), encrypted),
            )
            await db.commit()

    async def delete(self, owner):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA secure_delete=ON")
            await db.execute("DELETE FROM credentials WHERE owner=?", (str(owner),))
            await db.commit()


def parse_callback(value):
    try:
        parts = urlsplit(value.strip())
        codes = parse_qs(parts.query).get("code", [])
        valid = (
            parts.scheme == "http"
            and parts.netloc == "localhost"
            and parts.path == "/redirect"
            and not parts.fragment
            and len(codes) == 1
            and bool(codes[0])
        )
        if valid:
            return codes[0]
    except ValueError:
        pass
    raise ShopError("Expected the complete http://localhost/redirect?code=... URL.")


def token_claims(token):
    # Correlation/expiry only, not signature verification. Identity is resolved
    # through Riot's authenticated userinfo endpoint, never from user-supplied JWTs.
    try:
        return json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "==="))
    except Exception:
        raise ShopError("Riot returned an unexpected login response.") from None


class RiotStoreClient:
    def __init__(self):
        self.version = None
        self.version_until = 0
        self.cooldown_until = 0

    async def request(self, method, url, *, token_request=False, **kwargs):
        if time.monotonic() < self.cooldown_until:
            raise ShopError("Riot is cooling down. Please try again later.")
        try:
            timeout = aiohttp.ClientTimeout(total=15, connect=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method, url, allow_redirects=False, **kwargs
                ) as response:
                    if response.status == 429:
                        try:
                            delay = max(
                                1,
                                min(
                                    3600, int(response.headers.get("Retry-After", "60"))
                                ),
                            )
                        except ValueError:
                            delay = 60
                        self.cooldown_until = time.monotonic() + delay
                        raise ShopError(
                            "Riot rate limit reached. Please try again later."
                        )
                    if response.status == 401:
                        raise LoginExpired(
                            "Shop authorization expired. Use /login again."
                        )
                    if response.status == 400 and token_request:
                        try:
                            data = await response.json()
                        except (ValueError, aiohttp.ClientError):
                            data = {}
                        if data.get("error") == "invalid_grant":
                            raise LoginExpired(
                                "Shop authorization expired. Use /login again."
                            )
                    if response.status != 200:
                        self.cooldown_until = time.monotonic() + 30
                        raise ShopError(
                            "Riot is unavailable or rejected this request. Try again later."
                        )
                    data = await response.json()
                    if not isinstance(data, dict):
                        raise ShopError("Riot returned an unexpected response.")
                    return data
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            self.cooldown_until = time.monotonic() + 10
            raise ShopError("Could not reach Riot. Please try again later.") from None

    async def versions(self):
        if self.version is None or time.monotonic() >= self.version_until:
            data = await self.request("GET", "https://valorant-api.com/v1/version")
            self.version = data["data"]
            self.version_until = time.monotonic() + 900
        return self.version

    async def tokens(self, **fields):
        version = await self.versions()
        return await self.request(
            "POST",
            "https://auth.riotgames.com/token",
            token_request=True,
            headers={
                "User-Agent": f"RiotClient/{version['riotClientBuild']} rso-auth (Windows;10;;Professional, x64)"
            },
            data={"client_id": "riot-client", **fields},
        )

    async def login(self, code, nonce):
        data = await self.tokens(
            grant_type="authorization_code",
            code=code,
            redirect_uri="http://localhost/redirect",
        )
        if token_claims(data["id_token"]).get("nonce") != nonce:
            raise ShopError("Login session mismatch. Start /login again.")
        if not data.get("refresh_token"):
            raise ShopError("No reusable authorization returned. Login was not saved.")
        headers = {"Authorization": "Bearer " + data["access_token"]}
        identity = await self.request(
            "GET", "https://auth.riotgames.com/userinfo", headers=headers
        )
        region = await self.request(
            "PUT",
            "https://riot-geo.pas.si.riotgames.com/pas/v1/product/valorant",
            headers=headers,
            json={"id_token": data["id_token"]},
        )
        account = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "puuid": str(uuid.UUID(identity["sub"])),
            "region": region["affinities"]["live"],
            "name": identity.get("acct", {}).get("game_name", "Player"),
            "tag": identity.get("acct", {}).get("tag_line", ""),
            "expires": float(token_claims(data["access_token"])["exp"]),
        }
        if account["region"] not in {"ap", "na", "eu", "kr", "br", "latam"}:
            raise ShopError("This region is not supported.")
        return account

    async def refresh(self, account):
        data = await self.tokens(
            grant_type="refresh_token", refresh_token=account["refresh_token"]
        )
        return {
            **account,
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", account["refresh_token"]),
            "expires": float(token_claims(data["access_token"])["exp"]),
        }

    async def identity(self, account):
        identity = await self.request(
            "GET",
            "https://auth.riotgames.com/userinfo",
            headers={"Authorization": "Bearer " + account["access_token"]},
        )
        if str(uuid.UUID(identity["sub"])) != account["puuid"]:
            raise ShopError("Account identity mismatch. Use /login again.")
        acct = identity.get("acct", {})
        return {
            **account,
            "name": acct.get("game_name") or account.get("name", "Player"),
            "tag": acct.get("tag_line", ""),
        }

    async def shop(self, account):
        headers = {"Authorization": "Bearer " + account["access_token"]}
        entitlement = await self.request(
            "POST",
            "https://entitlements.auth.riotgames.com/api/token/v1",
            headers=headers,
            json={},
        )
        version = await self.versions()
        platform = dict(
            platformType="PC",
            platformOS="Windows",
            platformOSVersion="10.0.19042.1.256.64bit",
            platformChipset="Unknown",
        )
        headers.update(
            {
                "X-Riot-Entitlements-JWT": entitlement["entitlements_token"],
                "X-Riot-ClientVersion": version["riotClientVersion"],
                "X-Riot-ClientPlatform": base64.b64encode(
                    json.dumps(platform).encode()
                ).decode(),
            }
        )
        result = await self.request(
            "POST",
            f"https://pd.{account['region']}.a.pvp.net/store/v3/storefront/{account['puuid']}",
            headers=headers,
            json={},
        )
        panel = result["SkinsPanelLayout"]
        prices = {
            offer["OfferID"]: offer.get("Cost", {}).get(
                "85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741"
            )
            for offer in panel.get("SingleItemStoreOffers", [])
        }
        return {
            "expires": time.time()
            + max(
                0, min(86400, int(panel["SingleItemOffersRemainingDurationInSeconds"]))
            ),
            "offers": [
                {"id": str(uuid.UUID(item)), "price": prices.get(item)}
                for item in panel["SingleItemOffers"][:4]
            ],
        }

    async def skin(self, item_id):
        data = await self.request(
            "GET",
            f"https://valorant-api.com/v1/weapons/skinlevels/{uuid.UUID(item_id)}",
        )
        skin = data["data"]
        icon = skin.get("displayIcon")
        if icon and (
            urlsplit(icon).scheme != "https"
            or urlsplit(icon).netloc != "media.valorant-api.com"
        ):
            icon = None
        return {"name": str(skin["displayName"])[:200], "icon": icon}


def account_label(account):
    if not account:
        return None
    name = str(account.get("name") or "Linked account")[:100]
    tag = str(account.get("tag") or "")[:50]
    return f"{name}#{tag}" if tag else name + " (tag unavailable)"


def parse_allowed_users(value):
    """Only an explicit '*' opens registration; missing/invalid config fails closed."""
    if value.strip() == "*":
        return None
    allowed = {int(item.strip()) for item in value.split(",") if item.strip()}
    if not allowed or len(allowed) > 100 or any(owner <= 0 for owner in allowed):
        raise ValueError("Configure '*' or 1-100 positive Discord user IDs")
    return allowed


class ShopService:
    def __init__(self, vault, client, allowed):
        self.vault, self.client = vault, client
        self.allowed = None if allowed is None else set(allowed)
        self.pending = {}
        self.cache = {}
        # Small private beta: one operation at a time also orders logout against
        # login/refresh, so an in-flight operation cannot resurrect credentials.
        self.lock = asyncio.Lock()

    def check(self, owner):
        if self.allowed is not None and owner not in self.allowed:
            raise ShopError("The shop feature is currently limited to invited testers.")

    def begin(self, owner):
        self.check(owner)
        now = time.monotonic()
        self.pending = {
            user: entry for user, entry in self.pending.items() if entry[2] > now
        }
        if owner not in self.pending and len(self.pending) >= 1000:
            raise ShopError(
                "Too many pending logins. Please try again in a few minutes."
            )
        attempt, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
        self.pending[owner] = (attempt, nonce, time.monotonic() + 300)
        url = "https://auth.riotgames.com/authorize?" + urlencode(
            dict(
                client_id="riot-client",
                redirect_uri="http://localhost/redirect",
                response_type="code",
                scope="openid link ban lol_region account offline_access",
                nonce=nonce,
            )
        )
        return attempt, url

    async def login(self, owner, attempt, callback):
        self.check(owner)
        async with self.lock:
            pending = self.pending.get(owner)
            if not pending or pending[0] != attempt or pending[2] < time.monotonic():
                raise ShopError(
                    "Login request expired or was replaced. Start /login again."
                )
            code = parse_callback(callback)
            del self.pending[owner]  # one use, including upstream failure
            account = await self.client.login(code, pending[1])
            await self.vault.put(owner, account)
            self.cache.pop(owner, None)
            return account_label(account)

    async def linked_account(self, owner):
        self.check(owner)
        async with self.lock:
            return account_label(await self.vault.get(owner))

    async def logout(self, owner):
        self.check(owner)
        async with self.lock:
            self.pending.pop(owner, None)
            self.cache.pop(owner, None)
            await self.vault.delete(owner)

    async def shop(self, owner):
        self.check(owner)
        async with self.lock:
            account = await self.vault.get(owner)
            if account is None:
                raise ShopError("Use /login to link your own Riot account first.")
            cached = self.cache.get(owner)
            if cached and cached["expires"] > time.time():
                return cached
            try:
                if account["expires"] <= time.time() + 120:
                    account = await self.client.refresh(account)
                    # Save rotated credentials before any later request can fail.
                    await self.vault.put(owner, account)
                result = await self.client.shop(account)
            except LoginExpired:
                await self.vault.delete(owner)
                self.cache.pop(owner, None)
                raise
            # Older encrypted records lack the tag; upgrade in place without
            # asking the user to relink or exposing tokens to presentation code.
            if not account.get("tag"):
                try:
                    account = await self.client.identity(account)
                    await self.vault.put(owner, account)
                except Exception:
                    # Identity decoration must not hide a successful shop.
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
            self.cache[owner] = result
            return result
