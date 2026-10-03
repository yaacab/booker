export type ContractDraftEvidence = {
  id: string;
  body: string;
  body_sha256: string | null;
  offer_version_id: string | null;
  template_version: string;
  legal_pack_version: string;
  effect: string;
};

const SHA256 = /^[0-9a-f]{64}$/;

export function contractDraftAckBody(contract: ContractDraftEvidence, otp: string) {
  const code = otp.trim();
  if (!code) throw new Error("Введите код технического подтверждения из уведомлений.");
  if (!contract.body_sha256 || !SHA256.test(contract.body_sha256)) {
    throw new Error("Черновик не привязан к проверяемому снимку. Обновите сделку.");
  }
  if (contract.effect !== "technical_draft_acknowledgement") {
    throw new Error("Эта версия черновика не допускает техническое подтверждение.");
  }
  return { otp: code, body_hash: contract.body_sha256 };
}

export function contractDraftStatus(confirmed: boolean): string {
  return confirmed ? "технически подтверждено" : "черновик ожидает подтверждения";
}
