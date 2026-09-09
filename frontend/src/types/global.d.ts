/** Ponte exposta pelo app de desktop (preload-app.js). Ausente no navegador. */
interface PonteProspectOS {
  desktop: true
  versao: string | null
  aoReceber: (evento: string, callback: (dados: unknown) => void) => () => void
}

interface Window {
  prospectOS?: PonteProspectOS
}
