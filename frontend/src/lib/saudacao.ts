/** A copy é gerada com a saudação da hora da GERAÇÃO - mas pode ser enviada
 * horas depois. Este helper troca "Bom dia/Boa tarde/Boa noite" pela saudação
 * da hora ATUAL no momento de copiar/abrir o WhatsApp. */

export function saudacaoAtual(): string {
  const hora = new Date().getHours()
  if (hora >= 5 && hora < 12) return "Bom dia"
  if (hora >= 12 && hora < 18) return "Boa tarde"
  return "Boa noite"
}

const REGEX_SAUDACAO = /\b(Bom dia|Boa tarde|Boa noite)\b/gi

export function ajustarSaudacao(texto: string): string {
  const atual = saudacaoAtual()
  return texto.replace(REGEX_SAUDACAO, (encontrada) =>
    // preserva o caso da primeira letra ("boa tarde" no meio da frase fica "boa noite")
    encontrada[0] === encontrada[0].toLowerCase()
      ? atual.toLowerCase()
      : atual
  )
}
