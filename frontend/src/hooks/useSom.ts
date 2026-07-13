import { useEffect, useState } from "react"

const SONS = {
  "busca-maps-concluida": "/sounds/busca-maps-concluida.mp3",
  "analise-instagram-concluida": "/sounds/analise-instagram-concluida.mp3",
  "followup-marcado": "/sounds/followup-marcado.mp3",
  "card-movido": "/sounds/card-movido.mp3",
  copiado: "/sounds/copiado.mp3",
  "lead-fechou": "/sounds/lead-fechou.mp3",
  "apagar-lead": "/sounds/apagar-lead.mp3",
} as const

export type NomeSom = keyof typeof SONS

const CHAVE_ATIVADO = "som-ativado"
const CHAVE_VOLUME = "som-volume"

function lerSomAtivado(): boolean {
  return localStorage.getItem(CHAVE_ATIVADO) !== "false"
}

function lerSomVolume(): number {
  const salvo = Number(localStorage.getItem(CHAVE_VOLUME))
  return Number.isFinite(salvo) && salvo >= 0 && salvo <= 1 ? salvo : 0.5
}

export function tocarSom(nome: NomeSom): void {
  if (!lerSomAtivado()) return
  try {
    const audio = new Audio(SONS[nome])
    audio.volume = lerSomVolume()
    audio.play().catch(() => {
      // navegador pode bloquear autoplay antes da primeira interação do usuário - ignora silenciosamente
    })
  } catch {
    // ignora falha de reprodução (arquivo ausente, navegador sem suporte, etc.)
  }
}

export function useConfigSom() {
  const [ativado, setAtivadoState] = useState(lerSomAtivado)
  const [volume, setVolumeState] = useState(lerSomVolume)

  useEffect(() => {
    localStorage.setItem(CHAVE_ATIVADO, String(ativado))
  }, [ativado])

  useEffect(() => {
    localStorage.setItem(CHAVE_VOLUME, String(volume))
  }, [volume])

  const testarSom = () => {
    const somAntes = lerSomAtivado()
    if (!somAntes) localStorage.setItem(CHAVE_ATIVADO, "true")
    tocarSom("copiado")
    if (!somAntes) localStorage.setItem(CHAVE_ATIVADO, String(ativado))
  }

  return {
    ativado,
    setAtivado: setAtivadoState,
    volume,
    setVolume: setVolumeState,
    testarSom,
  }
}
