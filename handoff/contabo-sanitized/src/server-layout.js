import "dotenv/config";

export const SERVER_IDS = {
  guild: process.env.DISCORD_GUILD_ID || "",
  categories: {
    information: process.env.CATEGORY_INFORMATION_ID || "",
    administration: process.env.CATEGORY_ADMINISTRATION_ID || "",
    subscriber: process.env.CATEGORY_SUBSCRIBER_ID || ""
  },
  channels: {
    entry: process.env.ENTRY_CHANNEL_ID || "",
    news: process.env.NEWS_CHANNEL_ID || "",
    resources: process.env.RESOURCES_CHANNEL_ID || "",
    faq: process.env.FAQ_CHANNEL_ID || "",
    sales: process.env.SALES_CHANNEL_ID || "",
    logs: process.env.LOG_CHANNEL_ID || "",
    commands: process.env.COMMANDS_CHANNEL_ID || "",
    test: process.env.TEST_CHANNEL_ID || "",
    salesControl: process.env.SALES_CONTROL_CHANNEL_ID || "",
    staffVoice: process.env.STAFF_VOICE_CHANNEL_ID || "",
    support: process.env.SUPPORT_CHANNEL_ID || "",
    start: process.env.START_CHANNEL_ID || "",
    versions: process.env.VERSIONS_CHANNEL_ID || "",
    activation: process.env.ACTIVATION_CHANNEL_ID || "",
    tutorials: process.env.TUTORIALS_CHANNEL_ID || "",
    feedbackBeta: process.env.FEEDBACK_BETA_CHANNEL_ID || "",
    commercial: process.env.COMMERCIAL_CHANNEL_ID || "",
    meetingVoice: process.env.MEETING_VOICE_CHANNEL_ID || "",
    temporaryVoice: process.env.TEMPORARY_VOICE_CHANNEL_ID || ""
  }
};

export const CATEGORY_LAYOUT = [
  { key: "information", name: "📌・CONHEÇA O ALBIONMKT", position: 1, audience: "visitor" },
  { key: "subscriber", name: "💎・ÁREA DO ASSINANTE", position: 2, audience: "subscriber" },
  { key: "administration", name: "🛡️・ADMINISTRAÇÃO", position: 3, audience: "staff" }
];

export const CHANNEL_LAYOUT = [
  {
    key: "entry",
    name: "🚪・comece-aqui",
    parent: null,
    position: 0,
    audience: "entry",
    topic: "Conheça o AlbionMKT e confirme sua entrada para acessar o servidor."
  },
  {
    key: "news",
    name: "📣・novidades",
    parent: "information",
    position: 0,
    audience: "visitor",
    topic: "Comunicados oficiais, novidades e atualizações importantes do AlbionMKT."
  },
  {
    key: "resources",
    name: "✨・recursos-do-programa",
    parent: "information",
    position: 1,
    audience: "visitor",
    topic: "Conheça os recursos e benefícios do AlbionMKT."
  },
  {
    key: "sales",
    name: "💳・planos-e-assinatura",
    parent: "information",
    position: 2,
    audience: "visitor",
    topic: "Planos Venda, Compra e MKT Completo, com pagamento e liberação automática."
  },
  {
    key: "faq",
    name: "❓・duvidas-frequentes",
    parent: "information",
    position: 3,
    audience: "visitor",
    topic: "Respostas rápidas sobre pagamento, acesso, instalação, key e suporte."
  },
  {
    key: "start",
    name: "🚀・primeiros-passos",
    parent: "subscriber",
    position: 0,
    audience: "subscriber",
    topic: "Guia inicial para instalar, ativar e utilizar o AlbionMKT."
  },
  {
    key: "versions",
    name: "📦・versoes-e-atualizacoes",
    parent: "subscriber",
    position: 1,
    audience: "subscriber",
    topic: "Histórico de versões, correções e novidades do programa AlbionMKT."
  },
  {
    key: "activation",
    name: "🔑・ativacao",
    parent: "subscriber",
    position: 2,
    audience: "subscriber",
    topic: "Instruções para ativar sua key de acesso ao AlbionMKT."
  },
  {
    key: "tutorials",
    name: "📚・guias-e-tutoriais",
    parent: "subscriber",
    position: 3,
    audience: "subscriber",
    topic: "Guias objetivos e boas práticas para aproveitar o AlbionMKT."
  },
  {
    key: "support",
    name: "🎫・suporte",
    parent: "subscriber",
    position: 4,
    audience: "subscriber",
    topic: "Abra um atendimento privado com a equipe do AlbionMKT."
  },
  {
    key: "feedbackBeta",
    name: "🧪・feedback-beta",
    parent: "subscriber",
    position: 5,
    audience: "subscriber",
    topic: "Fórum privado para bugs, sugestões e feedback dos testadores do AlbionMKT."
  },
  {
    key: "logs",
    name: "📋・logs",
    parent: "administration",
    position: 0,
    audience: "staff",
    topic: "Registro privado das operações de entrada, pagamento, assinatura e suporte."
  },
  {
    key: "salesControl",
    name: "📊・controle-de-vendas",
    parent: "administration",
    position: 1,
    audience: "staff",
    topic: "Registro privado e automático das vendas e assinaturas do AlbionMKT."
  },
  {
    key: "commands",
    name: "🛠️・comandos-bot",
    parent: "administration",
    position: 2,
    audience: "staff",
    topic: "Comandos administrativos e orientações de operação do bot."
  },
  {
    key: "test",
    name: "🧪・teste",
    parent: "administration",
    position: 3,
    audience: "staff",
    topic: "Canal preservado para testes internos dos comandos do AlbionMKT."
  },
  { key: "staffVoice", name: "🔒・staff", parent: "administration", position: 4, audience: "staff" },
  { key: "meetingVoice", name: "📞・reuniao", parent: "administration", position: 5, audience: "staff" }
];
