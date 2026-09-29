import path from "node:path";
import { AttachmentBuilder, EmbedBuilder } from "discord.js";
import { config } from "./config.js";
import { BRAND, commercialButtons, entryButtons, salesButtons, supportButtons } from "./interaction-ui.js";
import { SERVER_IDS } from "./server-layout.js";

const bannerPath = path.resolve("assets", "albionmkt-welcome-banner.png");

async function upsertPanel(client, channelId, marker, payload) {
  const channel = await client.channels.fetch(channelId);
  if (!channel?.isTextBased()) throw new Error(`Canal de painel inválido: ${channelId}`);
  const messages = await channel.messages.fetch({ limit: 100 });
  const markers = Array.isArray(marker) ? marker : [marker];
  const existingPanels = [...messages.values()].filter((message) =>
    message.author.id === client.user.id &&
    message.embeds.some((item) => markers.includes(item.footer?.text))
  );
  const existing = existingPanels[0];
  const body = { content: "", ...payload };
  if (existing) {
    if (payload.files?.length) body.attachments = [];
    const updated = await existing.edit(body);
    for (const duplicate of existingPanels.slice(1)) await duplicate.delete().catch(() => null);
    return updated;
  }
  return channel.send(body);
}

function marked(embed, marker) {
  return embed.setFooter({ text: marker });
}

export async function publishPanels(client) {
  const ids = SERVER_IDS.channels;
  const entryMarker = "painel-albionmkt-entrada-v3";
  const entry = marked(new EmbedBuilder()
    .setColor(BRAND.navy)
    .setTitle("Bem-vindo(a) ao AlbionMKT")
    .setDescription([
      "Transforme informações de mercado em decisões mais rápidas, organizadas e inteligentes.",
      "",
      "Para acessar o servidor, conheça o programa e conclua a introdução guiada. As etapas serão exibidas de forma privada e levam menos de um minuto."
    ].join("\n"))
    .addFields(
      { name: "Acesso progressivo", value: "A área pública é liberada após a introdução. A área exclusiva é liberada somente após a confirmação do pagamento." },
      { name: "Privacidade", value: "Nunca publique senhas, tokens, dados completos de pagamento ou sua key." }
    )
    .setImage("attachment://albionmkt-welcome-banner.png"), entryMarker);

  const resourcesMarker = "painel-albionmkt-recursos-v2";
  const resources = marked(new EmbedBuilder()
    .setColor(BRAND.navy)
    .setTitle("Recursos do AlbionMKT")
    .setDescription("Uma central de apoio para análise, organização e tomada de decisão no mercado.")
    .addFields(
      { name: "📊 Análise de mercado", value: "Compare informações e identifique oportunidades com mais clareza." },
      { name: "🧭 Organização e rotas", value: "Planeje atividades e consulte recursos de mapa em uma única ferramenta." },
      { name: "⚙️ Fluxo simplificado", value: "Centralize tarefas repetitivas e reduza o tempo gasto em consultas manuais." },
      { name: "🔄 Evolução contínua", value: "Receba versões, melhorias, guias e suporte durante a assinatura." }
    ), resourcesMarker);

  const faqMarker = "painel-albionmkt-faq-v3";
  const faq = marked(new EmbedBuilder()
    .setColor(BRAND.navy)
    .setTitle("Dúvidas frequentes")
    .addFields(
      { name: "Como recebo o programa?", value: "Depois da aprovação, o bot envia por mensagem privada um link pessoal e temporário para download." },
      { name: "Como recebo a key?", value: "A key individual é enviada na mesma mensagem privada de confirmação." },
      { name: "Por quanto tempo tenho acesso?", value: "Venda, Compra e MKT Completo concedem 30 dias de acesso." },
      { name: "Posso repetir o teste gratis?", value: "Nao. Cada usuario do Discord pode utilizar o teste gratis somente uma vez." },
      { name: "Posso compartilhar a key?", value: "Não. A key e os links de download são pessoais e não podem ser compartilhados." },
      { name: "Onde peço ajuda?", value: "Assinantes podem abrir um atendimento privado no canal de suporte." }
    ), faqMarker);

  const salesMarker = "painel-albionmkt-assinatura-v3";
  const sales = marked(new EmbedBuilder()
    .setColor(BRAND.copper)
    .setTitle("Planos AlbionMKT")
    .setDescription("Escolha o produto desejado. Cada botão gera um checkout individual vinculado à sua conta do Discord.")
    .addFields(
      { name: "1. VENDA — R$ 39,90", value: "Venda os itens disponíveis na mochila.\nAcesso por 30 dias." },
      { name: "2. COMPRA — R$ 49,90", value: "Criação contínua de ordens de compra.\nAcesso por 30 dias." },
      { name: "3. MKT COMPLETO — R$ 99,90", value: "Compra, coleta, venda e retorno automático às compras.\nInclui a integração do ciclo completo.\nAcesso por 30 dias." },
      { name: "Por que o MKT Completo custa R$ 10,10 a mais?", value: "Venda + Compra totalizam R$ 89,80. O adicional corresponde ao ciclo automático integrado entre comprar, coletar, vender e retornar às compras." },
      { name: "Liberação", value: "Após a confirmação, cargo, key e download são enviados automaticamente por mensagem privada." },
      { name: "Pagamento seguro", value: "Confira o plano e o valor antes de concluir o pagamento no Mercado Pago." }
    ), salesMarker);

  const policiesMarker = "painel-albionmkt-politicas-v3";
  const policies = marked(new EmbedBuilder()
    .setColor(BRAND.navy)
    .setTitle("Políticas de acesso e entrega")
    .setDescription([
      "• A key e o link temporário de download são pessoais.",
      "• O arquivo é entregue somente por mensagem privada após a aprovação do pagamento.",
      "• Não compartilhe key, link, comprovante, senha ou token.",
      "• Cada plano concede 30 dias de acesso aos módulos contratados.",
      "• Em caso de falha na mensagem privada, habilite DMs e procure o suporte privado."
    ].join("\n")), policiesMarker);

  const startMarker = "painel-albionmkt-primeiros-passos-v2";
  const start = marked(new EmbedBuilder()
    .setColor(BRAND.navy)
    .setTitle("Primeiros passos")
    .setDescription([
      "1. Localize a mensagem privada enviada pelo bot após a compra.",
      "2. Baixe o arquivo pelo link pessoal e temporário.",
      "3. Extraia o programa em uma pasta do computador.",
      "4. Consulte o canal de ativação e informe sua key quando solicitado.",
      "5. Leia os guias antes de iniciar o uso."
    ].join("\n"))
    .addFields({ name: "Não recebeu a mensagem?", value: "Ative mensagens diretas deste servidor e abra um ticket no suporte." }), startMarker);

  const versionsMarker = "painel-albionmkt-versoes-v2";
  const versions = marked(new EmbedBuilder()
    .setColor(BRAND.navy)
    .setTitle("Versões e atualizações")
    .setDescription("Este canal apresenta notas de versão, correções e orientações de atualização.")
    .addFields({ name: "Download", value: "Por segurança, o arquivo não é publicado neste canal. O link pessoal é entregue por mensagem privada." }), versionsMarker);

  const activationMarker = "painel-albionmkt-ativacao-v2";
  const activation = marked(new EmbedBuilder()
    .setColor(BRAND.copper)
    .setTitle("Ativação da key")
    .setDescription([
      "• Abra o AlbionMKT e localize a tela de ativação.",
      "• Utilize exatamente a key recebida por mensagem privada.",
      "• Não adicione espaços antes ou depois da key.",
      "• Nunca publique a key em canais ou capturas de tela."
    ].join("\n"))
    .addFields({ name: "Problemas na ativação", value: "Abra um atendimento privado no suporte e informe apenas a mensagem de erro." }), activationMarker);

  const tutorialsMarker = "painel-albionmkt-tutoriais-v2";
  const tutorials = marked(new EmbedBuilder()
    .setColor(BRAND.navy)
    .setTitle("Guias e tutoriais")
    .setDescription("Os conteúdos serão organizados por objetivo, com instruções curtas, imagens e versão compatível do programa.")
    .addFields(
      { name: "Instalação", value: "Preparação do computador e primeira execução." },
      { name: "Configuração", value: "Ajustes recomendados e calibração inicial." },
      { name: "Uso diário", value: "Fluxos para aproveitar os recursos com segurança." }
    ), tutorialsMarker);

  const supportMarker = "painel-albionmkt-suporte";
  const support = marked(new EmbedBuilder()
    .setColor(BRAND.copper)
    .setTitle("Suporte privado")
    .setDescription("Abra um ticket para falar com a equipe sem expor seus dados no canal.")
    .addFields(
      { name: "Antes de abrir", value: "Informe o problema, a versão do programa e a mensagem de erro apresentada." },
      { name: "Segurança", value: "Nunca envie senha, token, key completa ou dados completos de pagamento." }
    ), supportMarker);

  const commercialMarker = "painel-albionmkt-atendimento-comercial-v3";
  const commercial = marked(new EmbedBuilder()
    .setColor(BRAND.copper)
    .setTitle("Vamos encontrar o plano certo para você")
    .setDescription([
      "Escolha uma opção nos botões abaixo para receber a resposta imediatamente.",
      "",
      "Escolha **Venda**, **Compra** ou **MKT Completo**. O checkout será criado de forma individual e privada."
    ].join("\n"))
    .addFields(
      { name: "1. VENDA — R$ 39,90", value: "Venda os itens disponíveis na mochila. Acesso por 30 dias." },
      { name: "2. COMPRA — R$ 49,90", value: "Criação contínua de ordens de compra. Acesso por 30 dias." },
      { name: "3. MKT COMPLETO — R$ 99,90", value: "Compra, coleta, venda e retorno automático às compras. Inclui a integração do ciclo completo. Acesso por 30 dias." },
      { name: "Ciclo integrado", value: "O MKT Completo custa R$ 10,10 a mais que Venda + Compra por incluir o ciclo automático integrado." },
      { name: "Não publique", value: "E-mail, nome completo, key, comprovante, dados de pagamento, senha ou token." }
    ), commercialMarker);

  const commandsMarker = "painel-albionmkt-comandos";
  const commands = marked(new EmbedBuilder()
    .setColor(BRAND.navy)
    .setTitle("Comandos do AlbionMKT")
    .addFields(
      { name: "/status", value: "Mostra o estado dos serviços." },
      { name: "/assinar", value: "Gera um checkout individual para Venda, Compra ou MKT Completo." },
      { name: "/pagar-pix", value: "Gera o mesmo checkout individual com Pix selecionado." },
      { name: "/minha-assinatura", value: "Consulta o acesso atual." },
      { name: "/suporte", value: "Abre um atendimento privado." },
      { name: "/ajuda", value: "Exibe orientações resumidas." }
    ), commandsMarker);

  const logsMarker = "painel-albionmkt-logs";
  const logs = marked(new EmbedBuilder()
    .setColor(BRAND.navy)
    .setTitle("Registro operacional ativo")
    .setDescription("Este canal recebe eventos automáticos de entrada, pagamentos, assinaturas e atendimentos."), logsMarker);

  const definitions = [
    [config.entryChannelId || ids.entry, [entryMarker, "painel-albionmkt-entrada-v2"], { embeds: [entry], components: entryButtons(), files: [new AttachmentBuilder(bannerPath, { name: "albionmkt-welcome-banner.png" })] }],
    [ids.resources, resourcesMarker, { embeds: [resources] }],
    [ids.faq, [faqMarker, "painel-albionmkt-faq-v2"], { embeds: [faq] }],
    [ids.faq, policiesMarker, { embeds: [policies] }],
    [config.salesChannelId || ids.sales, [salesMarker, "painel-albionmkt-assinatura"], { embeds: [sales], components: salesButtons() }],
    [ids.start, startMarker, { embeds: [start] }],
    [ids.versions, versionsMarker, { embeds: [versions] }],
    [ids.activation, activationMarker, { embeds: [activation] }],
    [ids.tutorials, tutorialsMarker, { embeds: [tutorials] }],
    [config.supportChannelId || ids.support, supportMarker, { embeds: [support], components: supportButtons() }],
    [ids.commercial, commercialMarker, { embeds: [commercial], components: commercialButtons() }],
    [ids.commands, commandsMarker, { embeds: [commands] }],
    [config.logChannelId || ids.logs, logsMarker, { embeds: [logs] }]
  ];

  const results = [];
  for (const [channelId, marker, payload] of definitions) {
    results.push(await upsertPanel(client, channelId, marker, payload));
  }
  return results.map((message) => message.id);
}
