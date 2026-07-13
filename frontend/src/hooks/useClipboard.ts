import { useEffect, useRef, useState } from "react"
import { tocarSom } from "@/hooks/useSom"

export function useClipboard(duracaoMs = 1500) {
  const [copiado, setCopiado] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  const copiar = async (texto: string) => {
    if (!texto) return
    await navigator.clipboard.writeText(texto)
    setCopiado(true)
    tocarSom("copiado")
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setCopiado(false), duracaoMs)
  }

  return { copiado, copiar }
}
