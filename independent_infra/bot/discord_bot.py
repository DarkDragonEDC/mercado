from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import aiohttp
import discord
from discord import app_commands


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} nao configurado")
    return value


BOT_TOKEN = required("DISCORD_BOT_TOKEN")
ADMIN_TOKEN = required("ALBIONMKT_ADMIN_TOKEN")
BACKEND_URL = os.getenv("ALBIONMKT_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0") or 0)
ADMIN_ROLE_IDS = {
    int(value)
    for value in os.getenv("DISCORD_ADMIN_ROLE_IDS", "").split(",")
    if value.strip().isdigit()
}


def module_ids(option: str) -> list[str]:
    return {
        "completo": ["purchase_orders", "sales_orders"],
        "compra": ["purchase_orders"],
        "venda": ["sales_orders"],
    }[option]


def is_admin(interaction: discord.Interaction) -> bool:
    if GUILD_ID and interaction.guild_id != GUILD_ID:
        return False
    member = interaction.user
    if isinstance(member, discord.Member):
        if member.guild_permissions.administrator:
            return True
        return bool({role.id for role in member.roles} & ADMIN_ROLE_IDS)
    return False


async def ensure_admin(interaction: discord.Interaction) -> bool:
    if is_admin(interaction):
        return True
    await interaction.response.send_message(
        "Voce nao possui permissao para administrar licencas.", ephemeral=True
    )
    return False


class BackendError(RuntimeError):
    pass


class AlbionMKTBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.http_session: aiohttp.ClientSession | None = None

    async def setup_hook(self) -> None:
        self.http_session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            timeout=aiohttp.ClientTimeout(total=15),
        )
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def close(self) -> None:
        if self.http_session:
            await self.http_session.close()
        await super().close()

    async def api(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        assert self.http_session is not None
        async with self.http_session.request(
            method, f"{BACKEND_URL}{path}", json=payload
        ) as response:
            try:
                body = await response.json()
            except aiohttp.ContentTypeError as exc:
                raise BackendError(f"API respondeu HTTP {response.status}") from exc
            if response.status >= 400:
                detail = body.get("detail") or body.get("message") or "erro desconhecido"
                raise BackendError(str(detail))
            return body


bot = AlbionMKTBot()


@bot.event
async def on_ready() -> None:
    if GUILD_ID:
        for guild in list(bot.guilds):
            if guild.id != GUILD_ID:
                await guild.leave()
    print(f"Bot independente conectado como {bot.user} ({bot.user.id if bot.user else '?'})")


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    if GUILD_ID and guild.id != GUILD_ID:
        await guild.leave()


@bot.tree.command(name="licenca_criar", description="Cria uma nova licenca do AlbionMKT")
@app_commands.describe(
    usuario="Cliente que recebera a licenca",
    dias="Validade em dias",
    computadores="Quantidade maxima de computadores",
    modulos="Plano liberado",
)
@app_commands.choices(
    modulos=[
        app_commands.Choice(name="Compra + Venda", value="completo"),
        app_commands.Choice(name="Somente Compra", value="compra"),
        app_commands.Choice(name="Somente Venda", value="venda"),
    ]
)
async def create_license(
    interaction: discord.Interaction,
    usuario: discord.Member,
    dias: app_commands.Range[int, 1, 3650] = 30,
    computadores: app_commands.Range[int, 1, 25] = 1,
    modulos: app_commands.Choice[str] | None = None,
) -> None:
    if not await ensure_admin(interaction):
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        selected = modulos.value if modulos else "completo"
        data = await bot.api(
            "POST",
            "/api/admin/licenses",
            {
                "discord_user_id": str(usuario.id),
                "duration_days": dias,
                "device_limit": computadores,
                "modules": module_ids(selected),
                "notes": f"Criada pelo Discord por {interaction.user.id}",
            },
        )
    except BackendError as exc:
        await interaction.followup.send(f"Falha ao criar: {exc}", ephemeral=True)
        return
    await interaction.followup.send(
        "Licenca criada. A key aparece somente nesta resposta:\n"
        f"```{data['key']}```\n"
        f"ID: `{data['id']}`\nVence: `{data['expires_at']}`",
        ephemeral=True,
    )


@bot.tree.command(name="licenca_listar", description="Lista as licencas mais recentes")
async def list_licenses(
    interaction: discord.Interaction,
    limite: app_commands.Range[int, 1, 25] = 10,
) -> None:
    if not await ensure_admin(interaction):
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        rows = await bot.api("GET", f"/api/admin/licenses?limit={limite}")
    except BackendError as exc:
        await interaction.followup.send(f"Falha ao listar: {exc}", ephemeral=True)
        return
    if not rows:
        await interaction.followup.send("Nenhuma licenca cadastrada.", ephemeral=True)
        return
    lines = []
    now = datetime.now().astimezone()
    for item in rows:
        state = "revogada" if item["revoked_at"] else "ativa/expiracao controlada"
        lines.append(
            f"`{item['id'][:8]}` {item['key_preview']} — {state} — "
            f"{item['device_count']}/{item['device_limit']} PCs — <@{item['discord_user_id']}>"
        )
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="licenca_status", description="Mostra os totais do sistema de licencas")
async def license_stats(interaction: discord.Interaction) -> None:
    if not await ensure_admin(interaction):
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        stats = await bot.api("GET", "/api/admin/stats")
    except BackendError as exc:
        await interaction.followup.send(f"Falha ao consultar: {exc}", ephemeral=True)
        return
    await interaction.followup.send(
        "**Controle de licencas independente**\n"
        f"Ativas: **{stats['active']}**\n"
        f"Expiram em 7 dias: **{stats['expires_within_7_days']}**\n"
        f"Expiradas: **{stats['expired']}**\n"
        f"Revogadas: **{stats['revoked']}**\n"
        f"Computadores: **{stats['devices']}**\n"
        f"Total: **{stats['total']}**",
        ephemeral=True,
    )


@bot.tree.command(name="licenca_revogar", description="Revoga uma licenca pelo ID")
async def revoke_license(interaction: discord.Interaction, id: str) -> None:
    if not await ensure_admin(interaction):
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await bot.api("POST", f"/api/admin/licenses/{id}/revoke")
    except BackendError as exc:
        await interaction.followup.send(f"Falha ao revogar: {exc}", ephemeral=True)
        return
    await interaction.followup.send(f"Licenca `{id}` revogada.", ephemeral=True)


@bot.tree.command(name="licenca_resetar", description="Remove os computadores vinculados a uma licenca")
async def reset_license(interaction: discord.Interaction, id: str) -> None:
    if not await ensure_admin(interaction):
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await bot.api("POST", f"/api/admin/licenses/{id}/reset-devices")
    except BackendError as exc:
        await interaction.followup.send(f"Falha ao resetar: {exc}", ephemeral=True)
        return
    await interaction.followup.send(
        f"Computadores da licenca `{id}` removidos.", ephemeral=True
    )


@bot.tree.command(name="licenca_prorrogar", description="Prorroga uma licenca pelo ID")
async def extend_license(
    interaction: discord.Interaction,
    id: str,
    dias: app_commands.Range[int, 1, 3650],
) -> None:
    if not await ensure_admin(interaction):
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        data = await bot.api(
            "POST", f"/api/admin/licenses/{id}/extend", {"days": dias}
        )
    except BackendError as exc:
        await interaction.followup.send(f"Falha ao prorrogar: {exc}", ephemeral=True)
        return
    await interaction.followup.send(
        f"Licenca `{id}` prorrogada ate `{data['expires_at']}`.", ephemeral=True
    )


if __name__ == "__main__":
    bot.run(BOT_TOKEN, log_handler=None)
