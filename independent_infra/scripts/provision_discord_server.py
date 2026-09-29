from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import aiohttp


API_BASE = "https://discord.com/api/v10"
APP_ID = "1541423850707750982"
EXPECTED_GUILD_ID = "1541428118533967972"

VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
READ_MESSAGE_HISTORY = 1 << 16
USE_APPLICATION_COMMANDS = 1 << 31

CHANNEL_ACCESS = (
    VIEW_CHANNEL
    | SEND_MESSAGES
    | EMBED_LINKS
    | ATTACH_FILES
    | READ_MESSAGE_HISTORY
    | USE_APPLICATION_COMMANDS
)

ROLE_SPECS = (
    {"name": "🎓・Fundador", "color": 0xF1C40F, "hoist": True},
    {"name": "🎓・Admin", "color": 0xE74C3C, "hoist": True},
    {"name": "🧪・Beta", "color": 0x9B59B6, "hoist": True},
    {"name": "💎・Cliente", "color": 0x3498DB, "hoist": True},
    {"name": "👤・Visitante", "color": 0x95A5A6, "hoist": False},
)

CATEGORY_SPECS = (
    {"name": "📍・COMECE AQUI", "access": "public"},
    {"name": "📌・CONHEÇA O ALBIONMKT", "access": "visitor"},
    {"name": "💎・ÁREA DO CLIENTE", "access": "client"},
    {"name": "🛡️・ADMINISTRAÇÃO", "access": "admin"},
    {"name": "🔊・CANAIS DE VOZ", "access": "visitor"},
)

TEXT_CHANNELS = (
    ("📍・COMECE AQUI", "🚪・comece-aqui", "Regras, segurança e orientação inicial do AlbionMKT."),
    ("📍・COMECE AQUI", "👋・recepção", "Recepção e avisos iniciais do servidor independente."),
    ("📌・CONHEÇA O ALBIONMKT", "📣・novidades", "Novidades oficiais do AlbionMKT."),
    ("📌・CONHEÇA O ALBIONMKT", "✨・recursos-do-programa", "Recursos e módulos disponíveis no programa."),
    ("📌・CONHEÇA O ALBIONMKT", "💳・planos-e-acesso", "Planos, formas de acesso e informações comerciais."),
    ("📌・CONHEÇA O ALBIONMKT", "❓・duvidas-frequentes", "Respostas para as dúvidas mais comuns."),
    ("📌・CONHEÇA O ALBIONMKT", "📸・demonstracoes-e-resultados", "Demonstrações e resultados do AlbionMKT."),
    ("📌・CONHEÇA O ALBIONMKT", "💬・atendimento-comercial", "Canal de atendimento comercial."),
    ("📌・CONHEÇA O ALBIONMKT", "📜・termos-e-politicas", "Termos, políticas e orientações de uso."),
    ("💎・ÁREA DO CLIENTE", "🚀・primeiros-passos", "Configuração inicial para clientes."),
    ("💎・ÁREA DO CLIENTE", "📦・versoes-e-atualizacoes", "Versões e atualizações disponíveis."),
    ("💎・ÁREA DO CLIENTE", "🔑・ativacao", "Orientações para ativação da licença."),
    ("💎・ÁREA DO CLIENTE", "📚・guias-e-tutoriais", "Guias de utilização do AlbionMKT."),
    ("💎・ÁREA DO CLIENTE", "🎫・suporte", "Atendimento técnico para clientes."),
    ("💎・ÁREA DO CLIENTE", "📘・conta-alt", "Orientações para contas alternativas."),
    ("💎・ÁREA DO CLIENTE", "🧪・feedback-beta", "Feedbacks e testes de versões beta."),
    ("🛡️・ADMINISTRAÇÃO", "📋・logs", "Registros administrativos do ambiente independente."),
    ("🛡️・ADMINISTRAÇÃO", "📊・controle-de-vendas", "Controle privado de vendas e pagamentos."),
    ("🛡️・ADMINISTRAÇÃO", "🛠️・comandos-bot", "Comandos administrativos do bot independente."),
    ("🛡️・ADMINISTRAÇÃO", "🔐・controle-de-licencas", "Gestão privada de licenças e dispositivos."),
)

VOICE_CHANNELS = (
    ("🔊・CANAIS DE VOZ", "🌐・público"),
    ("🛡️・ADMINISTRAÇÃO", "📞・reunião"),
    ("🛡️・ADMINISTRAÇÃO", "🧪・teste-interno"),
)


def load_env(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(
            f"Arquivo de configuracao ausente: {path}. "
            "Crie-o com scripts/bootstrap_env.py e configure o Discord."
        )
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


class DiscordApi:
    def __init__(self, token: str) -> None:
        self.session = aiohttp.ClientSession(
            headers={"Authorization": f"Bot {token}"},
            timeout=aiohttp.ClientTimeout(total=30),
        )

    async def close(self) -> None:
        await self.session.close()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with self.session.request(method, f"{API_BASE}{path}", **kwargs) as response:
            if response.status == 429:
                data = await response.json()
                await asyncio.sleep(float(data.get("retry_after", 1)))
                return await self.request(method, path, **kwargs)
            if response.status == 204:
                return None
            data = await response.json()
            if response.status >= 400:
                raise RuntimeError(f"Discord HTTP {response.status}: {data}")
            return data


def role_overwrite(role_id: str) -> dict[str, str | int]:
    return {"id": role_id, "type": 0, "allow": str(CHANNEL_ACCESS), "deny": "0"}


def category_overwrites(
    access: str,
    guild_id: str,
    role_ids: dict[str, str],
    bot_role_id: str,
) -> list[dict[str, str | int]]:
    if access == "public":
        return []
    allowed_names = ["🎓・Fundador", "🎓・Admin"]
    if access == "visitor":
        allowed_names.extend(["👤・Visitante", "💎・Cliente", "🧪・Beta"])
    if access == "client":
        allowed_names.extend(["💎・Cliente", "🧪・Beta"])
    overwrites: list[dict[str, str | int]] = [
        {"id": guild_id, "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL)}
    ]
    overwrites.extend(role_overwrite(role_ids[name]) for name in allowed_names)
    overwrites.append(role_overwrite(bot_role_id))
    return overwrites


async def ensure_roles(
    api: DiscordApi,
    guild_id: str,
    roles: list[dict[str, Any]],
    apply: bool,
) -> tuple[dict[str, str], str]:
    by_name = {role["name"]: role for role in roles}
    role_ids: dict[str, str] = {}
    for spec in ROLE_SPECS:
        existing = by_name.get(spec["name"])
        if existing:
            role_ids[spec["name"]] = existing["id"]
            if apply:
                await api.request(
                    "PATCH",
                    f"/guilds/{guild_id}/roles/{existing['id']}",
                    json={**spec, "permissions": "0", "mentionable": False},
                )
            print(f"cargo presente: {spec['name']}")
        else:
            print(f"cargo a criar: {spec['name']}")
            if apply:
                created = await api.request(
                    "POST",
                    f"/guilds/{guild_id}/roles",
                    json={**spec, "permissions": "0", "mentionable": False},
                )
                role_ids[spec["name"]] = created["id"]

    bot_role = next(
        (
            role
            for role in roles
            if role.get("tags", {}).get("bot_id") == APP_ID
            or (role.get("managed") and role.get("name") == "AlbionMKT Independent")
        ),
        None,
    )
    if not bot_role:
        raise RuntimeError("Cargo gerenciado do bot independente nao encontrado")
    return role_ids, bot_role["id"]


async def ensure_categories(
    api: DiscordApi,
    guild_id: str,
    channels: list[dict[str, Any]],
    role_ids: dict[str, str],
    bot_role_id: str,
    apply: bool,
) -> dict[str, str]:
    categories = {channel["name"]: channel for channel in channels if channel["type"] == 4}
    rename_sources = {
        "📍・COMECE AQUI": "Canais de Texto",
        "🔊・CANAIS DE VOZ": "Canais de Voz",
    }
    category_ids: dict[str, str] = {}
    for position, spec in enumerate(CATEGORY_SPECS):
        existing = categories.get(spec["name"])
        if not existing and rename_sources.get(spec["name"]):
            existing = categories.get(rename_sources[spec["name"]])
        payload = {
            "name": spec["name"],
            "type": 4,
            "position": position,
            "permission_overwrites": category_overwrites(
                spec["access"], guild_id, role_ids, bot_role_id
            ),
        }
        if existing:
            category_ids[spec["name"]] = existing["id"]
            print(f"categoria presente/renomear: {spec['name']}")
            if apply:
                await api.request(
                    "PATCH", f"/channels/{existing['id']}", json=payload
                )
        else:
            print(f"categoria a criar: {spec['name']}")
            if apply:
                created = await api.request(
                    "POST", f"/guilds/{guild_id}/channels", json=payload
                )
                category_ids[spec["name"]] = created["id"]
    return category_ids


async def ensure_text_channels(
    api: DiscordApi,
    guild_id: str,
    channels: list[dict[str, Any]],
    category_ids: dict[str, str],
    apply: bool,
) -> None:
    by_name = {channel["name"]: channel for channel in channels if channel["type"] == 0}
    general = by_name.get("geral")
    for category_name, name, topic in TEXT_CHANNELS:
        existing = by_name.get(name)
        if name == "👋・recepção" and not existing:
            existing = general
        payload = {
            "name": name,
            "type": 0,
            "parent_id": category_ids[category_name],
            "topic": topic,
        }
        if existing:
            print(f"canal de texto presente/renomear: {name}")
            if apply:
                await api.request("PATCH", f"/channels/{existing['id']}", json=payload)
        else:
            print(f"canal de texto a criar: {name}")
            if apply:
                await api.request("POST", f"/guilds/{guild_id}/channels", json=payload)


async def ensure_voice_channels(
    api: DiscordApi,
    guild_id: str,
    channels: list[dict[str, Any]],
    category_ids: dict[str, str],
    apply: bool,
) -> None:
    by_name = {channel["name"]: channel for channel in channels if channel["type"] == 2}
    general = by_name.get("Geral")
    for category_name, name in VOICE_CHANNELS:
        existing = by_name.get(name)
        if name == "🌐・público" and not existing:
            existing = general
        payload = {"name": name, "type": 2, "parent_id": category_ids[category_name]}
        if existing:
            print(f"canal de voz presente/renomear: {name}")
            if apply:
                await api.request("PATCH", f"/channels/{existing['id']}", json=payload)
        else:
            print(f"canal de voz a criar: {name}")
            if apply:
                await api.request("POST", f"/guilds/{guild_id}/channels", json=payload)


async def reorder_channels(api: DiscordApi, guild_id: str) -> None:
    channels = await api.request("GET", f"/guilds/{guild_id}/channels")
    by_name = {channel["name"]: channel for channel in channels}
    updates: list[dict[str, Any]] = []

    for category_position, category in enumerate(CATEGORY_SPECS):
        category_channel = by_name[category["name"]]
        updates.append({"id": category_channel["id"], "position": category_position})

    children_by_category: dict[str, list[str]] = {
        category["name"]: [] for category in CATEGORY_SPECS
    }
    for category_name, name, _topic in TEXT_CHANNELS:
        children_by_category[category_name].append(name)
    for category_name, name in VOICE_CHANNELS:
        children_by_category[category_name].append(name)

    for category_name, child_names in children_by_category.items():
        for child_position, name in enumerate(child_names):
            updates.append(
                {
                    "id": by_name[name]["id"],
                    "position": child_position,
                }
            )

    await api.request("PATCH", f"/guilds/{guild_id}/channels", json=updates)


async def verify_state(api: DiscordApi, guild: dict[str, Any]) -> None:
    guild_id = guild["id"]
    roles = await api.request("GET", f"/guilds/{guild_id}/roles")
    channels = await api.request("GET", f"/guilds/{guild_id}/channels")
    owner = await api.request(
        "GET", f"/guilds/{guild_id}/members/{guild['owner_id']}"
    )
    bot_role = next(
        role
        for role in roles
        if role.get("tags", {}).get("bot_id") == APP_ID
        or (role.get("managed") and role.get("name") == "AlbionMKT Independent")
    )
    founder_role = next(role for role in roles if role["name"] == "🎓・Fundador")
    custom_role_names = {spec["name"] for spec in ROLE_SPECS}
    print(
        "auditoria: "
        f"categorias={sum(channel['type'] == 4 for channel in channels)}, "
        f"texto={sum(channel['type'] == 0 for channel in channels)}, "
        f"voz={sum(channel['type'] == 2 for channel in channels)}, "
        f"cargos={sum(role['name'] in custom_role_names for role in roles)}, "
        f"fundador_atribuido={founder_role['id'] in owner['roles']}, "
        f"permissoes_bot={bot_role['permissions']}"
    )


async def provision(apply: bool) -> None:
    root = Path(__file__).resolve().parents[1]
    load_env(root / ".env")
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    guild_id = os.environ.get("DISCORD_GUILD_ID", "").strip()
    if not token or not guild_id:
        raise RuntimeError("DISCORD_BOT_TOKEN e DISCORD_GUILD_ID sao obrigatorios")
    if guild_id != EXPECTED_GUILD_ID:
        raise RuntimeError(f"ID de servidor inesperado: {guild_id}")

    api = DiscordApi(token)
    try:
        guild = await api.request("GET", f"/guilds/{guild_id}")
        if guild["name"] != "AlbionMKT Independent - Testes":
            raise RuntimeError(f"Servidor inesperado: {guild['name']}")
        roles = await api.request("GET", f"/guilds/{guild_id}/roles")
        channels = await api.request("GET", f"/guilds/{guild_id}/channels")
        print(f"alvo confirmado: {guild['name']} ({guild_id})")
        print(f"modo: {'APLICAR' if apply else 'SIMULAR'}")

        role_ids, bot_role_id = await ensure_roles(api, guild_id, roles, apply)
        if apply:
            await api.request(
                "PUT",
                f"/guilds/{guild_id}/members/{guild['owner_id']}/roles/{role_ids['🎓・Fundador']}",
            )
            roles = await api.request("GET", f"/guilds/{guild_id}/roles")
            channels = await api.request("GET", f"/guilds/{guild_id}/channels")

        if apply or len(role_ids) == len(ROLE_SPECS):
            category_ids = await ensure_categories(
                api, guild_id, channels, role_ids, bot_role_id, apply
            )
            if apply:
                channels = await api.request("GET", f"/guilds/{guild_id}/channels")
            await ensure_text_channels(api, guild_id, channels, category_ids, apply)
            await ensure_voice_channels(api, guild_id, channels, category_ids, apply)
            if apply:
                await reorder_channels(api, guild_id)
        else:
            print("categorias e canais serao configurados apos a criacao dos cargos")

        if apply:
            print("configuracao concluida")
            print("admin_role_ids=" + ",".join([role_ids["🎓・Fundador"], role_ids["🎓・Admin"]]))
        if len(role_ids) == len(ROLE_SPECS):
            await verify_state(api, guild)
    finally:
        await api.close()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Configura o servidor Discord independente")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica as alteracoes; sem esta opcao apenas simula",
    )
    args = parser.parse_args()
    asyncio.run(provision(args.apply))


if __name__ == "__main__":
    main()
