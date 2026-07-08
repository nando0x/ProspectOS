import { Link } from "react-router-dom"
import { BookOpen, MapPin, Plus, Settings, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/layout/ThemeToggle"
import { InstagramIcon } from "@/components/icons/InstagramIcon"

interface HeaderProps {
  onNovaBusca?: () => void
  onVerIgnorados?: () => void
}

export function Header({ onNovaBusca, onVerIgnorados }: HeaderProps) {
  return (
    <header className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2">
          <img src="/logo-icon.svg" alt="ProspectOS" className="size-9" />
          <h1 className="text-lg font-semibold tracking-tight sm:text-xl">
            ProspectOS
          </h1>
        </Link>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/leads">
              <MapPin className="size-4" />
              <span className="hidden sm:inline">Google Maps</span>
            </Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/instagram">
              <InstagramIcon className="size-4" />
              <span className="hidden sm:inline">Instagram</span>
            </Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/documentacao">
              <BookOpen className="size-4" />
              <span className="hidden sm:inline">Documentação</span>
            </Link>
          </Button>
          {onVerIgnorados && (
            <Button variant="ghost" size="sm" onClick={onVerIgnorados}>
              <Trash2 className="size-4" />
              <span className="hidden sm:inline">Ignorados</span>
            </Button>
          )}
          {onNovaBusca && (
            <Button size="sm" onClick={onNovaBusca}>
              <Plus className="size-4" />
              <span className="hidden sm:inline">Nova busca</span>
            </Button>
          )}
          <Button variant="ghost" size="sm" asChild>
            <Link to="/configuracoes" aria-label="Configurações de API">
              <Settings className="size-4" />
            </Link>
          </Button>
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
