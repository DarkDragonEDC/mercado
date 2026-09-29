export async function deliverPrivateMessage(client, discordUserId, content, downloadPrepared) {
  try {
    const user = await client.users.fetch(discordUserId);
    await user.send(content);
    return { dmDelivered: true, downloadPrepared: Boolean(downloadPrepared) };
  } catch (error) {
    return {
      dmDelivered: false,
      downloadPrepared: Boolean(downloadPrepared),
      errorMessage: String(error?.message || "Falha ao enviar mensagem privada").slice(0, 300)
    };
  }
}
