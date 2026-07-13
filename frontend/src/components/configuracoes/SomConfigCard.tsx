import { Volume2, VolumeX } from "lucide-react"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Button } from "@/components/ui/button"
import { useConfigSom } from "@/hooks/useSom"

export function SomConfigCard() {
  const { ativado, setAtivado, volume, setVolume, testarSom } = useConfigSom()

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {ativado ? (
            <Volume2 className="size-4 text-muted-foreground" />
          ) : (
            <VolumeX className="size-4 text-muted-foreground" />
          )}
          <h3 className="font-medium">Sons do sistema</h3>
        </div>
        <Switch
          checked={ativado}
          onCheckedChange={setAtivado}
          aria-label="Ativar sons do sistema"
        />
      </div>

      <p className="text-sm text-muted-foreground">
        Sons curtos ao concluir buscas, marcar follow-up, mover leads no
        Kanban, copiar mensagens e outras ações.
      </p>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label>Volume</Label>
          <span className="text-xs text-muted-foreground">
            {Math.round(volume * 100)}%
          </span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            disabled={!ativado}
            onChange={(e) => setVolume(Number(e.target.value))}
            className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-muted accent-primary disabled:cursor-not-allowed disabled:opacity-50"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!ativado}
            onClick={testarSom}
          >
            Testar
          </Button>
        </div>
      </div>
    </div>
  )
}
