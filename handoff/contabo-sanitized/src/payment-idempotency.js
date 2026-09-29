export class PaymentIdempotencyGuard {
  #processing = new Set();

  async run(paymentId, wasProcessed, operation) {
    const id = String(paymentId || "");
    if (!id) throw new Error("Pagamento sem identificador.");
    if (this.#processing.has(id)) return { duplicate: true };
    if (await wasProcessed(id)) return { duplicate: true };
    if (this.#processing.has(id)) return { duplicate: true };
    this.#processing.add(id);
    try {
      if (await wasProcessed(id)) return { duplicate: true };
      return { duplicate: false, value: await operation() };
    } finally {
      this.#processing.delete(id);
    }
  }
}
