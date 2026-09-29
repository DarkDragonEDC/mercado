from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

try:
    from .provision_discord_server import DiscordApi, EXPECTED_GUILD_ID, load_env
except ImportError:  # Execução direta: python scripts/publish_discord_panels.py
    from provision_discord_server import DiscordApi, EXPECTED_GUILD_ID, load_env


EXPECTED_GUILD_NAME = "AlbionMKT Independent - Testes"
BRAND_COLOR = 0xD4AF37
TEST_COLOR = 0xE67E22


PANELS: dict[str, dict[str, Any]] = {
    "🚪・comece-aqui": {
        "title": "Bem-vindo(a) ao AlbionMKT",
        "description": (
            "O AlbionMKT ajuda a organizar dados de mercado do Albion Online para "
            "comparação, compra e venda. Este é o ambiente independente de testes.\n\n"
            "**Comece por aqui**\n"
            "1. Conclua as perguntas de entrada.\n"
            "2. Conheça os recursos e os planos.\n"
            "3. Se já possui acesso, siga a ativação na Área do Cliente.\n\n"
            "🔒 Não publique keys, HWID, comprovantes ou dados pessoais em canais públicos."
        ),
        "color": TEST_COLOR,
        "footer": "albionmkt:comece-aqui:v2 | Ambiente de testes — pagamentos desativados",
    },
    "👋・recepção": {
        "title": "Recepção e orientação",
        "description": (
            "Use este canal para entender o servidor. O atendimento comercial fica em "
            "**💬・atendimento-comercial** e o suporte técnico de clientes em "
            "**🎫・suporte**.\n\n"
            "A equipe nunca solicitará sua senha do Albion Online, senha do Discord ou "
            "controle remoto do computador sem combinação prévia."
        ),
        "footer": "albionmkt:recepcao:v2",
    },
    "📣・novidades": {
        "title": "Novidades oficiais",
        "description": (
            "Canal somente para anúncios de versão, manutenção e mudanças de serviço. "
            "Considere oficial apenas o que for publicado aqui pela administração."
        ),
        "footer": "albionmkt:novidades:v2",
    },
    "✨・recursos-do-programa": {
        "title": "Recursos do AlbionMKT",
        "description": (
            "**Compra** — coleta e organiza ofertas para apoiar decisões de compra.\n"
            "**Venda** — registra e compara oportunidades de venda.\n"
            "**Completo** — reúne Compra + Venda no mesmo acesso.\n\n"
            "O programa auxilia a análise; não garante lucro, disponibilidade de itens "
            "nem ausência de variações de preço."
        ),
        "footer": "albionmkt:recursos:v2",
    },
    "💳・planos-e-acesso": {
        "title": "Planos e acesso por 30 dias",
        "description": (
            "**Venda — R$ 39,90**\n"
            "**Compra — R$ 49,90**\n"
            "**Completo — R$ 99,90**\n\n"
            "Cada pagamento libera **30 dias de acesso**. Não há renovação automática "
            "nem cobrança recorrente. Ao final do período, uma nova compra é opcional.\n\n"
            "🧪 Neste servidor de testes, pagamentos permanecem desativados até a "
            "validação final do fluxo comercial."
        ),
        "color": TEST_COLOR,
        "footer": "albionmkt:planos:v2 | Sem assinatura recorrente",
    },
    "❓・duvidas-frequentes": {
        "title": "Dúvidas frequentes",
        "description": (
            "**É assinatura?** Não. É um acesso avulso de 30 dias, sem renovação automática.\n\n"
            "**Funciona em qualquer computador?** O acesso é vinculado ao dispositivo "
            "conforme as regras da licença. Trocas legítimas devem ser tratadas no suporte.\n\n"
            "**O programa garante lucro?** Não. Preços, liquidez, taxas e decisões dentro "
            "do jogo continuam sob responsabilidade do usuário.\n\n"
            "**Quais são os requisitos recomendados?** Windows 10/11 64 bits, SSD, "
            "8 GB de RAM no mínimo (16 GB recomendados) e tela em 1920×1080 com escala de 100%."
        ),
        "footer": "albionmkt:faq:v2",
    },
    "📸・demonstracoes-e-resultados": {
        "title": "Demonstrações verificáveis",
        "description": (
            "Aqui serão publicados vídeos e exemplos identificados por versão. Resultados "
            "individuais são apenas demonstrações e não promessa de desempenho futuro."
        ),
        "footer": "albionmkt:demonstracoes:v2",
    },
    "💬・atendimento-comercial": {
        "title": "Atendimento comercial",
        "description": (
            "Antes de comprar, informe qual módulo deseja e tire suas dúvidas. Não envie "
            "comprovantes ou dados pessoais diretamente no canal. O fluxo de pagamento "
            "será liberado somente após o anúncio oficial de produção."
        ),
        "color": TEST_COLOR,
        "footer": "albionmkt:comercial:v2 | Pagamentos desativados em testes",
    },
    "📜・termos-e-politicas": {
        "title": "Uso responsável, privacidade e suporte",
        "description": (
            "O AlbionMKT é uma ferramenta independente e não é afiliado à Sandbox "
            "Interactive. O usuário é responsável por respeitar as regras do Albion Online.\n\n"
            "A licença e o dispositivo podem ser verificados para controle de acesso. Keys, "
            "identificadores e dados de suporte devem ser tratados em canais privados. "
            "Abuso, compartilhamento indevido, fraude ou tentativa de contornar a licença "
            "podem resultar em bloqueio.\n\n"
            "O programa não promete lucro nem elimina riscos de mercado ou de mudanças nas "
            "regras do jogo. Condições comerciais e de suporte devem ser aceitas antes do pagamento."
        ),
        "footer": "albionmkt:termos:v2",
    },
    "🚀・primeiros-passos": {
        "title": "Primeiros passos",
        "description": (
            "1. Baixe somente a versão publicada em **📦・versoes-e-atualizacoes**.\n"
            "2. Confira os requisitos e mantenha Windows e drivers atualizados.\n"
            "3. Ative sua key em **🔑・ativacao** sem expô-la no Discord.\n"
            "4. Faça a calibração na resolução e escala recomendadas.\n"
            "5. Execute um teste curto antes de uma coleta extensa."
        ),
        "footer": "albionmkt:primeiros-passos:v2",
    },
    "📦・versoes-e-atualizacoes": {
        "title": "Versões e atualizações",
        "description": (
            "Cada publicação deve informar versão, data, mudanças, limitações conhecidas e "
            "hash do arquivo quando disponível. Não instale arquivos enviados por mensagem privada."
        ),
        "footer": "albionmkt:versoes:v2",
    },
    "🔑・ativacao": {
        "title": "Ativação segura",
        "description": (
            "Insira a key somente dentro do programa oficial. Nunca publique a key ou o HWID "
            "no Discord. Em caso de troca legítima de computador, abra atendimento em "
            "**🎫・suporte** para análise e redefinição do dispositivo."
        ),
        "footer": "albionmkt:ativacao:v2",
    },
    "📚・guias-e-tutoriais": {
        "title": "Guias e tutoriais",
        "description": (
            "Siga os guias na ordem: instalação, ativação, calibração, teste curto e uso do "
            "módulo adquirido. Tutorial em vídeo: https://youtu.be/z_9M3yN2zNY\n\n"
            "Se a interface do jogo, a resolução ou a escala mudarem, refaça a calibração "
            "antes de coletar novos dados."
        ),
        "footer": "albionmkt:guias:v2",
    },
    "🎫・suporte": {
        "title": "Como pedir suporte",
        "description": (
            "Informe versão do programa, edição do Windows, resolução/escala, módulo usado, "
            "passos para reproduzir e mensagem de erro. Remova keys, HWID, nomes pessoais e "
            "outros dados sensíveis antes de enviar imagens ou logs."
        ),
        "footer": "albionmkt:suporte:v2",
    },
    "📘・conta-alt": {
        "title": "Conta alternativa e transferência de prata",
        "description": (
            "Use apenas métodos permitidos pelo jogo e contas sob sua responsabilidade. A "
            "organização por ilha/estação pode facilitar transferências, mas taxas, permissões "
            "e riscos devem ser conferidos no cliente do Albion Online. Nunca compartilhe senha."
        ),
        "footer": "albionmkt:conta-alt:v2",
    },
    "🛠️・comandos-bot": {
        "title": "Comandos administrativos disponíveis",
        "description": (
            "`/licenca_criar` · `/licenca_listar` · `/licenca_status`\n"
            "`/licenca_revogar` · `/licenca_resetar` · `/licenca_prorrogar`\n\n"
            "Os comandos comerciais públicos do servidor antigo não devem ser anunciados "
            "até estarem integrados e testados no backend independente."
        ),
        "footer": "albionmkt:comandos-admin:v2",
    },
}


def embed_payload(panel: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": panel["title"],
        "description": panel["description"],
        "color": panel.get("color", BRAND_COLOR),
        "footer": {"text": panel["footer"]},
    }


async def publish(apply: bool) -> None:
    root = Path(__file__).resolve().parents[1]
    load_env(root / ".env")
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    guild_id = os.environ.get("DISCORD_GUILD_ID", "").strip()
    if not token or guild_id != EXPECTED_GUILD_ID:
        raise RuntimeError("Credenciais do servidor independente ausentes ou incorretas")

    api = DiscordApi(token)
    try:
        guild = await api.request("GET", f"/guilds/{guild_id}")
        if guild["name"] != EXPECTED_GUILD_NAME:
            raise RuntimeError(f"Servidor inesperado: {guild['name']}")
        me = await api.request("GET", "/users/@me")
        channels = await api.request("GET", f"/guilds/{guild_id}/channels")
        by_name = {channel["name"]: channel for channel in channels}
        print(f"alvo confirmado: {guild['name']} ({guild_id})")
        print(f"modo: {'APLICAR' if apply else 'SIMULAR'}")

        for channel_name, panel in PANELS.items():
            channel = by_name.get(channel_name)
            if not channel:
                raise RuntimeError(f"Canal ausente: {channel_name}")
            messages = await api.request(
                "GET", f"/channels/{channel['id']}/messages?limit=100"
            )
            marker = panel["footer"].split(" | ", 1)[0]
            current = next(
                (
                    message
                    for message in messages
                    if message.get("author", {}).get("id") == me["id"]
                    and any(
                        embed.get("footer", {}).get("text", "").startswith(marker)
                        for embed in message.get("embeds", [])
                    )
                ),
                None,
            )
            action = "atualizar" if current else "publicar"
            print(f"{action}: {channel_name}")
            if not apply:
                continue
            payload = {
                "content": "",
                "embeds": [embed_payload(panel)],
                "allowed_mentions": {"parse": []},
            }
            if current:
                await api.request(
                    "PATCH",
                    f"/channels/{channel['id']}/messages/{current['id']}",
                    json=payload,
                )
            else:
                await api.request(
                    "POST", f"/channels/{channel['id']}/messages", json=payload
                )
    finally:
        await api.close()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Publica os paineis do Discord independente")
    parser.add_argument("--apply", action="store_true", help="Publica; sem a opção, simula")
    args = parser.parse_args()
    asyncio.run(publish(args.apply))


if __name__ == "__main__":
    main()
