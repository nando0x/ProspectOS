"""Testes do fluxo de IA (ia.py) - provedores mockados, nenhuma chamada de rede real.
Cobre o fallback, o cooldown, a arquitetura system+user, o perfil do vendedor,
o sorteio de fechamento server-side e os prompts."""

import pytest

import db
import ia


class ErroDeCota(Exception):
    """Simula o RateLimitError dos SDKs: carrega status_code 429."""

    status_code = 429


class ErroGenerico(Exception):
    pass


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch):
    """Zera o cooldown entre testes e, por padrão, configura os 3 provedores sem
    perfil de vendedor (cada teste sobrescreve db.obter_config se quiser outro cenário)."""
    monkeypatch.setattr(ia, "_provedores_em_cooldown", {})
    monkeypatch.setattr(
        db, "obter_config",
        lambda chave, default=None: "chave-fake" if chave in ("gemini", "groq", "nvidia") else default,
    )
    yield


def configurar_provedores(monkeypatch, perfil_vendedor=None, **geradores):
    """Substitui os geradores reais por fakes e configura só os provedores passados.
    Os fakes recebem a assinatura real: (system, user, temperatura=..., formato_json=...)."""
    perfil = perfil_vendedor or {}

    def obter_config_fake(chave, default=None):
        if chave in geradores:
            return "chave-fake"
        if chave in perfil:
            return perfil[chave]
        return default

    monkeypatch.setattr(db, "obter_config", obter_config_fake)
    for provedor, funcao in geradores.items():
        monkeypatch.setitem(ia.GERADORES, provedor, funcao)


def resposta_fixa(texto):
    return lambda system, user, temperatura=None, formato_json=False: texto


class TestExecutarComFallback:
    def test_usa_primeiro_provedor_disponivel(self, monkeypatch):
        configurar_provedores(monkeypatch, gemini=resposta_fixa("resposta do gemini"))

        resultado, provedor, avisos = ia.executar_com_fallback("system", "user")
        assert resultado == "resposta do gemini"
        assert provedor == "gemini"
        assert avisos == []

    def test_repassa_system_user_temperatura_e_formato(self, monkeypatch):
        chamadas = []

        def gemini_espiao(system, user, temperatura=None, formato_json=False):
            chamadas.append((system, user, temperatura, formato_json))
            return "ok"

        configurar_provedores(monkeypatch, gemini=gemini_espiao)

        ia.executar_com_fallback("persona", "dados", temperatura=0.2, formato_json=True)
        assert chamadas == [("persona", "dados", 0.2, True)]

    def test_cai_para_o_proximo_quando_primeiro_falha(self, monkeypatch):
        def gemini_quebrado(system, user, temperatura=None, formato_json=False):
            raise ErroGenerico("explodiu")

        configurar_provedores(
            monkeypatch, gemini=gemini_quebrado, groq=resposta_fixa("resposta do groq")
        )

        resultado, provedor, avisos = ia.executar_com_fallback("system", "user")
        assert resultado == "resposta do groq"
        assert provedor == "groq"
        assert len(avisos) == 1
        assert "Google Gemini" in avisos[0]

    def test_pula_provedor_nao_configurado(self, monkeypatch):
        chamadas = []

        def gemini_nao_deveria_rodar(system, user, temperatura=None, formato_json=False):
            chamadas.append("gemini")
            return "x"

        configurar_provedores(monkeypatch, nvidia=resposta_fixa("resposta da nvidia"))
        monkeypatch.setitem(ia.GERADORES, "gemini", gemini_nao_deveria_rodar)

        _resultado, provedor, _avisos = ia.executar_com_fallback("system", "user")
        assert provedor == "nvidia"
        assert chamadas == []

    def test_provedor_que_estoura_timeout_cai_para_o_proximo(self, monkeypatch):
        def gemini_pendurado(system, user, temperatura=None, formato_json=False):
            raise TimeoutError("request timed out")

        configurar_provedores(
            monkeypatch, gemini=gemini_pendurado, groq=resposta_fixa("resposta do groq")
        )

        resultado, provedor, _avisos = ia.executar_com_fallback("system", "user")
        assert resultado == "resposta do groq"
        assert provedor == "groq"

    def test_todos_falharam_levanta_com_ultimo_erro(self, monkeypatch):
        erro_groq = ErroGenerico("groq caiu")

        def falha_gemini(system, user, temperatura=None, formato_json=False):
            raise ErroGenerico("gemini caiu")

        def falha_groq(system, user, temperatura=None, formato_json=False):
            raise erro_groq

        configurar_provedores(monkeypatch, gemini=falha_gemini, groq=falha_groq)

        with pytest.raises(ia.NenhumProvedorDisponivel) as excecao:
            ia.executar_com_fallback("system", "user")
        assert excecao.value.erro_final is erro_groq

    def test_nenhum_configurado_levanta_com_erro_none(self, monkeypatch):
        configurar_provedores(monkeypatch)  # nenhum provedor

        with pytest.raises(ia.NenhumProvedorDisponivel) as excecao:
            ia.executar_com_fallback("system", "user")
        assert excecao.value.erro_final is None

    def test_parser_rejeitando_resposta_aciona_fallback(self, monkeypatch):
        configurar_provedores(
            monkeypatch,
            gemini=resposta_fixa("resposta que o parser rejeita"),
            groq=resposta_fixa("resposta boa"),
        )

        def parser(resposta):
            if "rejeita" in resposta:
                raise ValueError("formato inválido")
            return resposta.upper()

        resultado, provedor, _avisos = ia.executar_com_fallback("system", "user", parser=parser)
        assert resultado == "RESPOSTA BOA"
        assert provedor == "groq"


class TestCooldown:
    def test_erro_de_cota_poe_provedor_em_cooldown(self, monkeypatch):
        chamadas = []

        def gemini_sem_cota(system, user, temperatura=None, formato_json=False):
            chamadas.append("gemini")
            raise ErroDeCota("429 too many requests")

        configurar_provedores(monkeypatch, gemini=gemini_sem_cota, groq=resposta_fixa("ok"))

        _, provedor, _ = ia.executar_com_fallback("system", "user")
        assert provedor == "groq"
        assert chamadas == ["gemini"]
        assert ia._provedor_em_cooldown("gemini")

        _, provedor, avisos = ia.executar_com_fallback("system", "user")
        assert provedor == "groq"
        assert chamadas == ["gemini"]  # gemini nem foi tentado de novo
        assert any("cota gratuita" in aviso for aviso in avisos)

    def test_erro_generico_nao_gera_cooldown(self, monkeypatch):
        def gemini_quebrado(system, user, temperatura=None, formato_json=False):
            raise ErroGenerico("erro qualquer")

        configurar_provedores(monkeypatch, gemini=gemini_quebrado, groq=resposta_fixa("ok"))

        ia.executar_com_fallback("system", "user")
        assert not ia._provedor_em_cooldown("gemini")


class TestDeteccaoDeErroDeCota:
    def test_detecta_por_status_code(self):
        assert ia._e_erro_de_cota(ErroDeCota("qualquer texto"))

    def test_detecta_por_nome_da_classe(self):
        class RateLimitError(Exception):
            pass

        assert ia._e_erro_de_cota(RateLimitError("x"))

    def test_detecta_por_texto_como_ultimo_recurso(self):
        assert ia._e_erro_de_cota(Exception("Resource has been exhausted (e.g. check quota)."))

    def test_erro_comum_nao_e_cota(self):
        assert not ia._e_erro_de_cota(Exception("connection reset by peer"))


class TestSystemPrompt:
    def test_sem_perfil_usa_persona_neutra(self, monkeypatch):
        monkeypatch.setattr(db, "obter_config", lambda chave, default=None: default)
        system = ia.montar_system_copywriter("WhatsApp")
        assert "primeira pessoa do singular" in system
        assert "Quem envia as mensagens (escreva na voz dessa pessoa)" not in system

    def test_perfil_do_vendedor_entra_no_system(self, monkeypatch):
        perfil = {
            "vendedor_nome": "Fernando",
            "vendedor_apresentacao": "crio sites para negócios locais",
            "vendedor_diferencial": "entrego em 7 dias",
        }
        monkeypatch.setattr(db, "obter_config", lambda chave, default=None: perfil.get(chave, default))

        system = ia.montar_system_copywriter("WhatsApp")
        assert "Fernando" in system
        assert "crio sites para negócios locais" in system
        assert "entrego em 7 dias" in system

    def test_perfil_vem_com_instrucao_de_usar_o_que_faz(self, monkeypatch):
        """Só listar o perfil não basta: sem instrução explícita o modelo descreve a
        oferta com um genérico próprio e ignora o campo 'O que faz' (medido: 0/4)."""
        perfil = {
            "vendedor_nome": "Gabriel",
            "vendedor_apresentacao": "estruturo a presença digital completa de negócios locais",
            "vendedor_diferencial": "diagnóstico gratuito antes de qualquer proposta",
        }
        monkeypatch.setattr(db, "obter_config", lambda chave, default=None: perfil.get(chave, default))

        system = ia.montar_system_copywriter("WhatsApp")
        assert "ÚNICA fonte da verdade" in system
        assert "NUNCA substitua por uma descrição genérica" in system

    def test_sem_perfil_nao_tem_instrucao_de_fonte_da_verdade(self, monkeypatch):
        monkeypatch.setattr(db, "obter_config", lambda chave, default=None: default)
        assert "ÚNICA fonte da verdade" not in ia.montar_system_copywriter("WhatsApp")

    def test_proibe_inventar_nome_de_pessoa_e_contato_previo(self, monkeypatch):
        """Regressão: o modelo abriu com 'Boa tarde, Ana!' num lead institucional e
        alegou 'estou passando pela cidade'. Ambos são invenção pura."""
        monkeypatch.setattr(db, "obter_config", lambda chave, default=None: default)
        system = ia.montar_system_copywriter("WhatsApp")
        assert "NUNCA invente o nome de quem RECEBE" in system
        assert "NUNCA invente fatos sobre você" in system

    def test_proibicao_de_nome_nao_atinge_o_remetente(self, monkeypatch):
        """A 1a versão da regra derrubou a assinatura junto (3/12 -> 0/12): o modelo
        passou a evitar nomes em geral, inclusive o do próprio vendedor."""
        perfil = {
            "vendedor_nome": "Gabriel",
            "vendedor_apresentacao": "estruturo presença digital",
            "vendedor_diferencial": "diagnóstico gratuito",
        }
        monkeypatch.setattr(db, "obter_config", lambda chave, default=None: perfil.get(chave, default))

        system = ia.montar_system_copywriter("WhatsApp")
        assert "NÃO se aplica ao SEU nome" in system
        assert "meu nome é Gabriel" in system

    def test_exemplo_nao_carrega_oferta_concreta_pra_copiar(self, monkeypatch):
        """O exemplo trazia 'Eu crio sites profissionais para negócios locais' e o
        modelo copiava essa frase em vez de usar o perfil. A oferta virou lacuna."""
        monkeypatch.setattr(db, "obter_config", lambda chave, default=None: default)
        system = ia.montar_system_copywriter("WhatsApp")
        assert "Eu crio sites profissionais para negócios locais" not in system
        assert "<UMA FRASE COM O QUE VOCÊ FAZ, DERIVADA DO PERFIL ACIMA>" in system

    def test_exemplo_nao_usa_nome_de_pessoa_inventado(self, monkeypatch):
        """O exemplo abria com 'Janete' para um negócio chamado 'Estética Vit' - ou
        seja, demonstrava exatamente o comportamento que as regras proíbem."""
        monkeypatch.setattr(db, "obter_config", lambda chave, default=None: default)
        assert "Janete" not in ia.montar_system_copywriter("WhatsApp")

    def test_canal_muda_o_tom(self, monkeypatch):
        monkeypatch.setattr(db, "obter_config", lambda chave, default=None: default)
        assert "DM real" in ia.montar_system_copywriter("DM do Instagram")
        assert "DM real" not in ia.montar_system_copywriter("WhatsApp")

    def test_wrapper_envia_o_system_do_copywriter(self, monkeypatch):
        capturado = {}

        def espiao(system, user, temperatura=None, formato_json=False):
            capturado["system"] = system
            capturado["user"] = user
            return "mensagem"

        configurar_provedores(
            monkeypatch, perfil_vendedor={"vendedor_nome": "Fernando"}, gemini=espiao
        )

        ia.gerar_mensagem_com_fallback("Empresa X", "clínica", "Rua A", 4.8)
        assert "copywriter sênior" in capturado["system"]
        assert "Fernando" in capturado["system"]
        assert "Empresa X" in capturado["user"]


class TestSorteioDeFechamento:
    def test_pergunta_de_sim_nao(self, monkeypatch):
        monkeypatch.setattr(ia.random, "random", lambda: 0.1)  # < 0.5 → pergunta
        monkeypatch.setattr(ia.random, "choice", lambda opcoes: opcoes[0])

        fechamento = ia.sortear_fechamento()
        assert "pergunta de sim/não" in fechamento
        assert ia.PERGUNTAS_DE_FECHAMENTO[0] in fechamento

    def test_horario_concreto_em_dia_util(self, monkeypatch):
        monkeypatch.setattr(ia.random, "random", lambda: 0.9)  # >= 0.5 → horário
        monkeypatch.setattr(ia.random, "randint", lambda a, b: 1)
        monkeypatch.setattr(ia.random, "choice", lambda opcoes: opcoes[0])

        fechamento = ia.sortear_fechamento()
        assert "horário concreto" in fechamento
        assert any(dia in fechamento for dia in ia.NOMES_DIAS_UTEIS)
        assert "9h" in fechamento

    def test_fechamento_sorteado_entra_no_prompt(self, monkeypatch):
        monkeypatch.setattr(ia, "sortear_fechamento", lambda: "FECHAMENTO-SORTEADO")
        prompt = ia.montar_prompt_contato("Empresa", "clínica", "Rua A", 4.8)
        assert "FECHAMENTO-SORTEADO" in prompt


class TestPromptContato:
    def test_sem_site_usa_argumento_de_ausencia(self):
        prompt = ia.montar_prompt_contato("Empresa X", "clínica", "Rua A", 4.8)
        assert "NÃO possui site" in prompt

    def test_site_ruim_cita_problemas_e_oferece_reformulacao(self):
        prompt = ia.montar_prompt_contato(
            "Empresa X", "clínica", "Rua A", 4.8,
            site_status="site_ruim",
            site_problemas="não adaptado para celular; sem HTTPS",
        )
        assert "TEM um site" in prompt
        assert "não adaptado para celular; sem HTTPS" in prompt
        assert "NÃO possui site" not in prompt

    def test_conteudo_do_site_entra_no_prompt_quando_fornecido(self):
        prompt = ia.montar_prompt_contato(
            "Empresa X", "clínica", "Rua A", 4.8,
            site_status="site_ruim", site_problemas="sem HTTPS",
            conteudo_site="Título da página: Clínica X - promoção de 2023",
        )
        assert "promoção de 2023" in prompt
        assert "citar UM detalhe específico" in prompt

    def test_sem_conteudo_nao_tem_bloco(self):
        prompt = ia.montar_prompt_contato("Empresa X", "clínica", "Rua A", 4.8)
        assert "Conteúdo REAL do site" not in prompt

    def test_avaliacoes_cidade_e_instagram_entram_no_prompt(self):
        prompt = ia.montar_prompt_contato(
            "Empresa X", "clínica", "Rua A", 5.0,
            num_avaliacoes=105, cidade="Cuiabá",
            instagram_url="https://www.instagram.com/empresa_x/",
        )
        assert "105" in prompt
        assert "Cuiabá" in prompt
        assert "instagram.com/empresa_x" in prompt


class TestPromptFollowup:
    def test_followup_recebe_a_mensagem_anterior(self):
        prompt = ia.montar_prompt_followup(
            "Empresa X", "clínica", "Rua A", 4.8, follow_ups_enviados=1,
            mensagem_anterior="Olá! Vi que a Empresa X tem nota alta...",
        )
        assert "Vi que a Empresa X tem nota alta" in prompt
        assert "NÃO repita o argumento" in prompt

    def test_sem_mensagem_anterior_nao_tem_bloco(self):
        prompt = ia.montar_prompt_followup(
            "Empresa X", "clínica", "Rua A", 4.8, follow_ups_enviados=1,
        )
        assert "Mensagem já enviada anteriormente" not in prompt

    def test_wrapper_passa_mensagem_anterior(self, monkeypatch):
        capturado = {}

        def espiao(system, user, temperatura=None, formato_json=False):
            capturado["user"] = user
            return "followup"

        configurar_provedores(monkeypatch, gemini=espiao)

        ia.gerar_mensagem_com_fallback(
            "Empresa X", "clínica", "Rua A", 4.8, tipo="followup",
            follow_ups_enviados=2, mensagem_anterior="PRIMEIRA-MENSAGEM",
        )
        assert "PRIMEIRA-MENSAGEM" in capturado["user"]


class TestWrappers:
    def test_gerar_mensagem_sem_chave_tem_mensagem_amigavel(self, monkeypatch):
        configurar_provedores(monkeypatch)

        with pytest.raises(RuntimeError, match="Nenhuma chave de IA configurada"):
            ia.gerar_mensagem_com_fallback("Empresa", "Categoria", "Endereço", 4.5)

    def test_gerar_mensagem_todos_falharam_tem_mensagem_amigavel(self, monkeypatch):
        def falha(system, user, temperatura=None, formato_json=False):
            raise ErroGenerico("caiu")

        configurar_provedores(monkeypatch, gemini=falha)

        with pytest.raises(RuntimeError, match="Todos os provedores de IA configurados falharam"):
            ia.gerar_mensagem_com_fallback("Empresa", "Categoria", "Endereço", 4.5)


class TestClassificacao:
    def test_usa_json_mode_e_temperatura_baixa(self, monkeypatch):
        capturado = {}

        def espiao(system, user, temperatura=None, formato_json=False):
            capturado.update(system=system, temperatura=temperatura, formato_json=formato_json)
            return '{"prioridade": "alta", "nicho": "dentista", "justificativa": "x", "sugestao_dm": "oi"}'

        configurar_provedores(monkeypatch, gemini=espiao)

        resultado = ia.classificar_lead_instagram_com_fallback(
            {"username": "user1", "comentarios": []}, nicho_alvo=None
        )
        assert resultado["prioridade"] == "alta"
        assert capturado["formato_json"] is True
        assert capturado["temperatura"] == ia.TEMPERATURA_CLASSIFICACAO
        assert "JSON" in capturado["system"]

    def test_parseia_json_com_cerca_de_markdown(self, monkeypatch):
        resposta = """```json
{"prioridade": "Alta", "nicho": "dentista", "justificativa": "bio comercial", "sugestao_dm": "oi!"}
```"""
        configurar_provedores(monkeypatch, gemini=resposta_fixa(resposta))

        resultado = ia.classificar_lead_instagram_com_fallback(
            {"username": "user1", "comentarios": []}, nicho_alvo=None
        )
        assert resultado["prioridade"] == "alta"
        assert resultado["nicho"] == "dentista"
        assert resultado["sugestao_dm"] == "oi!"

    def test_prioridade_desconhecida_vira_baixa(self, monkeypatch):
        resposta = '{"prioridade": "urgente", "nicho": "", "justificativa": "", "sugestao_dm": ""}'
        configurar_provedores(monkeypatch, gemini=resposta_fixa(resposta))

        resultado = ia.classificar_lead_instagram_com_fallback(
            {"username": "user1", "comentarios": []}, nicho_alvo=None
        )
        assert resultado["prioridade"] == "baixa"

    def test_json_invalido_cai_para_proximo_provedor(self, monkeypatch):
        configurar_provedores(
            monkeypatch,
            gemini=resposta_fixa("isso não é JSON"),
            groq=resposta_fixa('{"prioridade": "media", "nicho": "", "justificativa": "", "sugestao_dm": ""}'),
        )

        resultado = ia.classificar_lead_instagram_com_fallback(
            {"username": "user1", "comentarios": []}, nicho_alvo=None
        )
        assert resultado["prioridade"] == "media"

    def test_sem_provedores_levanta_runtime_error(self, monkeypatch):
        configurar_provedores(monkeypatch)

        with pytest.raises(RuntimeError, match="nenhum provedor de IA conseguiu classificar"):
            ia.classificar_lead_instagram_com_fallback(
                {"username": "user1", "comentarios": []}, nicho_alvo=None
            )


class TestTraduzirErro:
    def test_cota(self):
        assert ia.traduzir_erro_ia(ErroDeCota("429")) == "cota gratuita excedida por agora"

    def test_timeout(self):
        assert ia.traduzir_erro_ia(Exception("request timeout")) == "demorou demais para responder"

    def test_indisponivel(self):
        assert ia.traduzir_erro_ia(Exception("503 service unavailable")) == "serviço indisponível no momento"

    def test_runtime_error_passa_direto(self):
        assert ia.traduzir_erro_ia(RuntimeError("mensagem específica")) == "mensagem específica"

    def test_erro_desconhecido_vira_mensagem_generica(self):
        assert "erro inesperado" in ia.traduzir_erro_ia(Exception("algo estranho"))
