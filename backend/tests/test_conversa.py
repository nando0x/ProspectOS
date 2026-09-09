"""Testes do cockpit de conversa: histórico por lead, dedup da captura,
vínculo por telefone e análise da negociação por IA.

Nada aqui toca rede nem o keyring real: a IA é substituída por monkeypatch e o
cofre de credenciais por um dict em memória.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import app as app_module
import db
import ia
import processar
import rotas_conversa


@pytest.fixture
def banco(tmp_path, monkeypatch):
    caminho = tmp_path / "leads_teste.db"
    monkeypatch.setattr(db, "CAMINHO_BANCO", caminho)
    cofre = {}
    monkeypatch.setattr(db, "_keyring_obter", cofre.get)
    monkeypatch.setattr(db, "_keyring_salvar", lambda c, v: cofre.update({c: v}) or True)
    monkeypatch.setattr(db, "_keyring_apagar", lambda c: cofre.pop(c, None))
    conexao = sqlite3.connect(caminho)
    processar.preparar_banco(conexao)
    conexao.close()
    return caminho


@pytest.fixture(autouse=True)
def limpar_lead_ativo():
    rotas_conversa._lead_ativo.update({"canal": None, "lead_ref": None, "telefone": None, "nome": None})
    yield


@pytest.fixture
def cliente(banco):
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def criar_lead(place_id="place-1", telefone="65996757327", nome="Estética Vitá"):
    conexao = db.conectar()
    try:
        conexao.execute(
            "INSERT INTO leads (place_id, nome, categoria, endereco, nota, num_avaliacoes, "
            "telefone, whatsapp_link, site_status, visto_em, atualizado_em) "
            "VALUES (?, ?, 'Clínica', 'Rua X', 5.0, 120, ?, ?, 'sem_site', '2026-07-01', '2026-07-01')",
            (place_id, nome, telefone, f"https://wa.me/55{telefone}"),
        )
        conexao.commit()
    finally:
        conexao.close()
    return place_id


# ---------------------------------------------------------------------------
# normalizar_telefone - o que faz o vínculo conversa↔lead funcionar
# ---------------------------------------------------------------------------

class TestNormalizarTelefone:
    def test_remove_ddi_55(self):
        assert rotas_conversa.normalizar_telefone("5565996757327") == "65996757327"

    def test_mantem_numero_sem_ddi(self):
        assert rotas_conversa.normalizar_telefone("65996757327") == "65996757327"

    def test_remove_mascara(self):
        assert rotas_conversa.normalizar_telefone("(65) 99675-7327") == "65996757327"

    def test_banco_e_whatsapp_convergem(self):
        # o cenário real: banco guarda sem DDI, WhatsApp reporta com
        assert (
            rotas_conversa.normalizar_telefone("65996757327")
            == rotas_conversa.normalizar_telefone("5565996757327@c.us")
        )

    def test_vazio_vira_none(self):
        assert rotas_conversa.normalizar_telefone("") is None
        assert rotas_conversa.normalizar_telefone(None) is None

    def test_fixo_de_10_digitos_preservado(self):
        assert rotas_conversa.normalizar_telefone("55) 6533221122") == "6533221122"


class TestVariantesTelefone:
    """O 9º dígito é a maior fonte de falso-negativo: leads capturados antigos
    podem estar sem ele, e o WhatsApp resolve o JID com ele (ou o contrário)."""

    def test_com_nono_gera_versao_sem(self):
        assert rotas_conversa._variantes_telefone("65996757327") == {"65996757327", "6596757327"}

    def test_sem_nono_gera_versao_com(self):
        assert rotas_conversa._variantes_telefone("6533221122") == {"6533221122", "65933221122"}

    def test_lead_antigo_casa_com_jid_novo(self):
        # banco com 10 dígitos, WhatsApp reportando 13 (DDI + 9º dígito)
        do_banco = rotas_conversa._variantes_telefone("6533221122")
        do_whatsapp = rotas_conversa._variantes_telefone("5565933221122")
        assert do_banco & do_whatsapp

    def test_numeros_diferentes_nao_casam(self):
        assert not (
            rotas_conversa._variantes_telefone("65996757327")
            & rotas_conversa._variantes_telefone("65991112222")
        )


# ---------------------------------------------------------------------------
# Histórico
# ---------------------------------------------------------------------------

class TestHistorico:
    def test_conversa_nova_vem_vazia(self, cliente):
        criar_lead()
        dados = cliente.get("/api/conversa/maps/place-1/mensagens").get_json()
        assert dados == {"mensagens": [], "analise": None}

    def test_lead_inexistente_404(self, cliente):
        assert cliente.get("/api/conversa/maps/nao-existe/mensagens").status_code == 404

    def test_canal_invalido_400(self, cliente):
        assert cliente.get("/api/conversa/telegram/x/mensagens").status_code == 400

    def test_adicionar_mensagem_manual(self, cliente):
        criar_lead()
        resposta = cliente.post(
            "/api/conversa/maps/place-1/mensagens",
            json={"autor": "lead", "texto": "Eu já tenho um Instagram"},
        )
        assert resposta.status_code == 200
        mensagens = resposta.get_json()["mensagens"]
        assert len(mensagens) == 1
        assert mensagens[0]["autor"] == "lead"
        assert mensagens[0]["origem"] == "manual"

    def test_autor_invalido_400(self, cliente):
        criar_lead()
        resposta = cliente.post(
            "/api/conversa/maps/place-1/mensagens", json={"autor": "robo", "texto": "oi"}
        )
        assert resposta.status_code == 400

    def test_texto_vazio_400(self, cliente):
        criar_lead()
        resposta = cliente.post(
            "/api/conversa/maps/place-1/mensagens", json={"autor": "lead", "texto": "   "}
        )
        assert resposta.status_code == 400

    def test_ordem_cronologica(self, cliente):
        criar_lead()
        for texto, quando in [("segunda", "2026-07-02T10:00:00"), ("primeira", "2026-07-01T10:00:00")]:
            cliente.post(
                "/api/conversa/maps/place-1/mensagens",
                json={"autor": "lead", "texto": texto, "enviada_em": quando},
            )
        mensagens = cliente.get("/api/conversa/maps/place-1/mensagens").get_json()["mensagens"]
        assert [m["texto"] for m in mensagens] == ["primeira", "segunda"]

    def test_duas_manuais_iguais_coexistem(self, cliente):
        # mensagem manual tem chave_dedup NULL: o UNIQUE não pode bloquear
        criar_lead()
        for _ in range(2):
            cliente.post("/api/conversa/maps/place-1/mensagens", json={"autor": "lead", "texto": "oi"})
        mensagens = cliente.get("/api/conversa/maps/place-1/mensagens").get_json()["mensagens"]
        assert len(mensagens) == 2

    def test_remover_mensagem(self, cliente):
        criar_lead()
        resposta = cliente.post(
            "/api/conversa/maps/place-1/mensagens", json={"autor": "lead", "texto": "apagar"}
        )
        mensagem_id = resposta.get_json()["mensagens"][0]["id"]
        resposta = cliente.delete(f"/api/conversa/maps/place-1/mensagens/{mensagem_id}")
        assert resposta.get_json()["mensagens"] == []


# ---------------------------------------------------------------------------
# Ingestão vinda da janela do WhatsApp
# ---------------------------------------------------------------------------

class TestIngestao:
    def test_vincula_pelo_telefone_com_ddi(self, cliente):
        criar_lead(telefone="65996757327")
        resposta = cliente.post("/api/conversa/ingestao", json={
            "telefone": "5565996757327",
            "mensagens": [
                {"autor": "vendedor", "texto": "Oi, tudo bem?", "enviada_em": "2026-07-26T00:35:00", "id_externo": "a1"},
                {"autor": "lead", "texto": "Eu já tenho um Instagram", "enviada_em": "2026-07-26T00:38:00", "id_externo": "a2"},
            ],
        })
        dados = resposta.get_json()
        assert dados["vinculado"] is True
        assert dados["novas"] == 2
        assert dados["lead_ref"] == "place-1"

    def test_telefone_desconhecido_nao_grava(self, cliente):
        criar_lead(telefone="65996757327")
        dados = cliente.post("/api/conversa/ingestao", json={
            "telefone": "5511999999999",
            "mensagens": [{"autor": "lead", "texto": "não sou lead", "id_externo": "z1"}],
        }).get_json()
        assert dados["vinculado"] is False
        assert dados["novas"] == 0

    def test_reingestao_nao_duplica(self, cliente):
        # o MutationObserver reenvia o que já está na tela a cada re-render
        criar_lead()
        lote = {
            "telefone": "5565996757327",
            "mensagens": [{"autor": "lead", "texto": "oi", "enviada_em": "2026-07-26T00:38:00", "id_externo": "m1"}],
        }
        assert cliente.post("/api/conversa/ingestao", json=lote).get_json()["novas"] == 1
        assert cliente.post("/api/conversa/ingestao", json=lote).get_json()["novas"] == 0

        mensagens = cliente.get("/api/conversa/maps/place-1/mensagens").get_json()["mensagens"]
        assert len(mensagens) == 1

    def test_dedup_sem_id_externo_usa_hash(self, cliente):
        criar_lead()
        lote = {
            "telefone": "5565996757327",
            "mensagens": [{"autor": "lead", "texto": "mesma coisa", "enviada_em": "2026-07-26T01:00:00"}],
        }
        cliente.post("/api/conversa/ingestao", json=lote)
        assert cliente.post("/api/conversa/ingestao", json=lote).get_json()["novas"] == 0

    def test_mesma_mensagem_em_horarios_diferentes_sao_duas(self, cliente):
        criar_lead()
        for quando in ["2026-07-26T01:00:00", "2026-07-26T02:00:00"]:
            cliente.post("/api/conversa/ingestao", json={
                "telefone": "5565996757327",
                "mensagens": [{"autor": "lead", "texto": "oi", "enviada_em": quando}],
            })
        mensagens = cliente.get("/api/conversa/maps/place-1/mensagens").get_json()["mensagens"]
        assert len(mensagens) == 2

    def test_ignora_mensagem_malformada(self, cliente):
        criar_lead()
        dados = cliente.post("/api/conversa/ingestao", json={
            "telefone": "5565996757327",
            "mensagens": [
                {"autor": "lead", "texto": "boa"},
                {"autor": "desconhecido", "texto": "autor inválido"},
                {"autor": "lead", "texto": ""},
                "isso nem é um objeto",
            ],
        }).get_json()
        assert dados["novas"] == 1

    def test_usuario_troca_de_conversa_cai_no_lead_certo(self, cliente):
        # lead ativo é A, mas a janela está mostrando a conversa de B
        criar_lead(place_id="lead-a", telefone="65911111111", nome="Lead A")
        criar_lead(place_id="lead-b", telefone="65922222222", nome="Lead B")
        cliente.post("/api/conversa/lead-ativo", json={"canal": "maps", "lead_ref": "lead-a"})

        dados = cliente.post("/api/conversa/ingestao", json={
            "telefone": "5565922222222",
            "mensagens": [{"autor": "lead", "texto": "aqui é o B", "id_externo": "b1"}],
        }).get_json()
        assert dados["lead_ref"] == "lead-b"

    def test_mensagens_nao_lista_400(self, cliente):
        assert cliente.post("/api/conversa/ingestao", json={"telefone": "x", "mensagens": "oi"}).status_code == 400

    def test_lead_antigo_sem_nono_digito_casa(self, cliente):
        criar_lead(telefone="6533221122")  # 10 dígitos, sem o 9
        dados = cliente.post("/api/conversa/ingestao", json={
            "telefone": "5565933221122",  # WhatsApp resolveu com o 9
            "mensagens": [{"autor": "lead", "texto": "oi", "id_externo": "v1"}],
        }).get_json()
        assert dados["vinculado"] is True


class TestEstadoCaptura:
    def test_sem_captura_esta_inativa(self, cliente):
        rotas_conversa._estado_captura.update({"visto_em": None})
        assert cliente.get("/api/conversa/estado-captura").get_json()["ativa"] is False

    def test_ingestao_marca_captura_viva(self, cliente):
        criar_lead()
        cliente.post("/api/conversa/ingestao", json={
            "telefone": "5565996757327",
            "mensagens": [{"autor": "lead", "texto": "oi", "id_externo": "c1"}],
        })
        estado = cliente.get("/api/conversa/estado-captura").get_json()
        assert estado["ativa"] is True
        assert estado["telefone"] == "65996757327"

    def test_heartbeat_antigo_fica_inativo(self, cliente):
        from datetime import datetime, timedelta
        antigo = (datetime.now() - timedelta(seconds=rotas_conversa.SEGUNDOS_CAPTURA_VIVA + 30))
        rotas_conversa._estado_captura.update({"visto_em": antigo.isoformat(timespec="seconds")})
        assert cliente.get("/api/conversa/estado-captura").get_json()["ativa"] is False


class TestLeadAtivo:
    def test_definir_e_obter(self, cliente):
        criar_lead()
        resposta = cliente.post("/api/conversa/lead-ativo", json={"canal": "maps", "lead_ref": "place-1"})
        assert resposta.status_code == 200
        dados = cliente.get("/api/conversa/lead-ativo").get_json()
        assert dados["lead_ref"] == "place-1"
        assert dados["telefone"] == "65996757327"  # já normalizado

    def test_lead_inexistente_404(self, cliente):
        assert cliente.post("/api/conversa/lead-ativo", json={"canal": "maps", "lead_ref": "x"}).status_code == 404

    def test_sem_lead_ref_400(self, cliente):
        assert cliente.post("/api/conversa/lead-ativo", json={}).status_code == 400


# ---------------------------------------------------------------------------
# Análise por IA
# ---------------------------------------------------------------------------

class TestParserAnalise:
    def test_json_completo(self):
        bruto = json.dumps({
            "estagio": "objecao",
            "leitura": "O lead valoriza o Instagram e não vê o site como necessário.",
            "objetivo": "Mostrar o site como complemento, não substituto.",
            "resposta_sugerida": "O Instagram pode seguir sendo seu canal principal...",
            "evitar": ["Dizer que Instagram não é profissional", "Falar de preço agora"],
        })
        analise = ia._parsear_analise_conversa(bruto)
        assert analise["estagio"] == "objecao"
        assert len(analise["evitar"]) == 2

    def test_remove_cercas_markdown(self):
        bruto = '```json\n{"estagio": "interesse", "leitura": "x", "objetivo": "y", "resposta_sugerida": "z", "evitar": []}\n```'
        assert ia._parsear_analise_conversa(bruto)["estagio"] == "interesse"

    def test_estagio_invalido_cai_no_padrao(self):
        bruto = '{"estagio": "inventado", "leitura": "", "objetivo": "", "resposta_sugerida": "", "evitar": []}'
        assert ia._parsear_analise_conversa(bruto)["estagio"] == "descoberta"

    def test_evitar_como_string_vira_lista(self):
        bruto = '{"estagio": "descoberta", "leitura": "", "objetivo": "", "resposta_sugerida": "", "evitar": "Falar de preço"}'
        assert ia._parsear_analise_conversa(bruto)["evitar"] == ["Falar de preço"]

    def test_evitar_truncado_no_limite(self):
        itens = [f"item {i}" for i in range(20)]
        bruto = json.dumps({"estagio": "descoberta", "leitura": "", "objetivo": "",
                            "resposta_sugerida": "", "evitar": itens})
        from constantes import MAX_ITENS_EVITAR
        assert len(ia._parsear_analise_conversa(bruto)["evitar"]) == MAX_ITENS_EVITAR

    def test_json_invalido_levanta(self):
        # o executar_com_fallback trata isso como falha e tenta o próximo provedor
        with pytest.raises(json.JSONDecodeError):
            ia._parsear_analise_conversa("desculpe, não consigo")

    def test_campos_ausentes_viram_vazio(self):
        assert ia._parsear_analise_conversa('{"estagio": "esfriou"}')["leitura"] == ""


class TestPromptAnalise:
    def test_historico_entra_na_transcricao(self):
        prompt = ia.montar_prompt_analise_conversa(
            {"nome": "Estética Vitá", "site_status": "sem_site"},
            [
                {"autor": "vendedor", "texto": "Oi, tudo bem?", "enviada_em": "2026-07-26T00:35:00"},
                {"autor": "lead", "texto": "Eu já tenho um Instagram", "enviada_em": "2026-07-26T00:38:00"},
            ],
        )
        assert "VOCÊ (vendedor): Oi, tudo bem?" in prompt
        assert "LEAD: Eu já tenho um Instagram" in prompt
        # a última fala do lead vira foco explícito
        assert 'A última mensagem do lead foi: "Eu já tenho um Instagram"' in prompt

    def test_conversa_vazia_avisa_no_prompt(self):
        prompt = ia.montar_prompt_analise_conversa({"nome": "X", "site_status": "sem_site"}, [])
        assert "nenhuma mensagem trocada ainda" in prompt

    def test_historico_longo_e_truncado(self):
        from constantes import MAX_MENSAGENS_NO_PROMPT
        mensagens = [
            {"autor": "lead", "texto": f"mensagem {i}", "enviada_em": "2026-07-26T00:00:00"}
            for i in range(MAX_MENSAGENS_NO_PROMPT + 15)
        ]
        prompt = ia.montar_prompt_analise_conversa({"nome": "X", "site_status": "sem_site"}, mensagens)
        assert "15 mensagem(ns) mais antiga(s) omitida(s)" in prompt
        assert "mensagem 0" not in prompt
        assert f"mensagem {MAX_MENSAGENS_NO_PROMPT + 14}" in prompt

    def test_sem_resposta_do_lead_e_sinalizado(self):
        prompt = ia.montar_prompt_analise_conversa(
            {"nome": "X", "site_status": "sem_site"},
            [{"autor": "vendedor", "texto": "Oi", "enviada_em": "2026-07-26T00:00:00"}],
        )
        assert "ainda não respondeu" in prompt


class TestRotaAnalisar:
    def _analise_fake(self, monkeypatch, estagio="objecao"):
        monkeypatch.setattr(ia, "analisar_conversa_com_fallback", lambda lead, msgs: (
            {
                "estagio": estagio,
                "leitura": "O lead valoriza o Instagram.",
                "objetivo": "Posicionar o site como complemento.",
                "resposta_sugerida": "O Instagram pode continuar sendo seu canal principal.",
                "evitar": ["Dizer que Instagram não é profissional"],
            },
            "gemini",
            [],
        ))

    def test_conversa_vazia_400(self, cliente):
        criar_lead()
        resposta = cliente.post("/api/conversa/maps/place-1/analisar")
        assert resposta.status_code == 400
        assert "ainda não há mensagens" in resposta.get_json()["erro"]

    def test_analise_com_sucesso(self, cliente, monkeypatch):
        criar_lead()
        cliente.post("/api/conversa/maps/place-1/mensagens", json={"autor": "lead", "texto": "Já tenho Instagram"})
        self._analise_fake(monkeypatch)

        dados = cliente.post("/api/conversa/maps/place-1/analisar").get_json()
        assert dados["estagio"] == "objecao"
        assert dados["provedor"] == "gemini"
        assert dados["mensagens_consideradas"] == 1

    def test_analise_fica_em_cache_no_historico(self, cliente, monkeypatch):
        criar_lead()
        cliente.post("/api/conversa/maps/place-1/mensagens", json={"autor": "lead", "texto": "oi"})
        self._analise_fake(monkeypatch, estagio="interesse")
        cliente.post("/api/conversa/maps/place-1/analisar")

        # reabrir a conversa traz a última análise sem chamar IA de novo
        dados = cliente.get("/api/conversa/maps/place-1/mensagens").get_json()
        assert dados["analise"]["estagio"] == "interesse"
        assert dados["analise"]["evitar"] == ["Dizer que Instagram não é profissional"]

    def test_todos_provedores_falharam_500_amigavel(self, cliente, monkeypatch):
        criar_lead()
        cliente.post("/api/conversa/maps/place-1/mensagens", json={"autor": "lead", "texto": "oi"})

        def falhar(lead, mensagens):
            raise ia.NenhumProvedorDisponivel("sem cota")

        monkeypatch.setattr(ia, "analisar_conversa_com_fallback", falhar)
        resposta = cliente.post("/api/conversa/maps/place-1/analisar")
        assert resposta.status_code == 500
        assert "Configurações" in resposta.get_json()["erro"]
