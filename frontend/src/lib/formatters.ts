export function formatarNota(nota: number | null): string {
  return nota === null || nota === undefined ? "-" : nota.toFixed(1)
}

export function formatarData(data: string | null): string {
  if (!data) return "-"
  const [ano, mes, dia] = data.split("-")
  if (!ano || !mes || !dia) return data
  return `${dia}/${mes}/${ano}`
}

export function formatarDataHora(iso: string): string {
  try {
    return new Date(iso).toLocaleString("pt-BR")
  } catch {
    return iso
  }
}

export function formatarTempoRelativo(data: string): string {
  const alvo = data.length === 10 ? new Date(`${data}T00:00:00`) : new Date(data)
  if (Number.isNaN(alvo.getTime())) return data

  const agora = new Date()
  const diffMs = agora.getTime() - alvo.getTime()
  const diffMin = Math.round(diffMs / 60_000)

  if (diffMin < 0) {
    return data.length === 10 ? formatarData(data) : formatarDataHora(data)
  }
  if (diffMin < 1) return "agora"
  if (diffMin < 60) return `há ${diffMin} minuto${diffMin === 1 ? "" : "s"}`

  const diffHoras = Math.round(diffMin / 60)
  if (diffHoras < 24) return `há ${diffHoras} hora${diffHoras === 1 ? "" : "s"}`

  const inicioHoje = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate())
  const inicioAlvo = new Date(alvo.getFullYear(), alvo.getMonth(), alvo.getDate())
  const diffDias = Math.round((inicioHoje.getTime() - inicioAlvo.getTime()) / 86_400_000)

  if (diffDias === 0) return "hoje"
  if (diffDias === 1) return "ontem"
  if (diffDias < 7) return `há ${diffDias} dias`

  return data.length === 10 ? formatarData(data) : formatarDataHora(data)
}

export function hojeISO(): string {
  const agora = new Date()
  const ano = agora.getFullYear()
  const mes = String(agora.getMonth() + 1).padStart(2, "0")
  const dia = String(agora.getDate()).padStart(2, "0")
  return `${ano}-${mes}-${dia}`
}

export function followupVencidoOuHoje(proximoFollowup: string | null): boolean {
  if (!proximoFollowup) return false
  return proximoFollowup <= hojeISO()
}

export function tagsParaLista(tags: string | null): string[] {
  if (!tags) return []
  return tags
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean)
}
