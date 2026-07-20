"""Testes da fonte Google Places API (fontes_maps.py) e das rotas de fonte/login.

Nada aqui toca a rede: a API do Google é simulada com monkeypatch em
requests.post, e o instagrapi com um módulo fake em sys.modules.
"""

import csv
import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import app as app_module
import db
import fontes_maps
import jobs
import paths
import processar


# ---------------------------------------------------------------------------
# Fakes da Places API
# ---------------------------------------------------------------------------

def _place(nome="Estética Vitá", nota=4.9, avaliacoes=120, telefone="(65) 3322-1122",
           site="", place_id="ChIJabc123", categoria="Clínica de estética"):
    return {
        "id": place_id,
        "displayName": {"text": nome},
        "primaryTypeDisplayName": {"text": categoria},
        "formattedAddress": "Av. Brasil, 100 - Cuiabá - MT",
        "rating": nota,
        "userRatingCount": avaliacoes,
        "nationalPhoneNumber": telefone,
        "websiteUri": site,
    }


class RespostaFake:
    def __init__(self, status_code=200, corpo=None):
        self.status_code = status_code
        self._corpo = corpo or {}

    def json(self):
        return self._corpo


# ---------------------------------------------------------------------------
# buscar_com_places_api → CSV no formato do scraper
# ---------------------------------------------------------------------------

class TestBuscarComPlacesApi:
    def test_escreve_csv_no_formato_do_scraper(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            fontes_maps.requests, "post",
            lambda *a, **kw: RespostaFake(200, {"places": [_place()]}),
        )
        arquivo = tmp_path / "bruto.csv"
        total = fontes_maps.buscar_com_places_api(["clínica de estética em Cuiabá"], arquivo, "chave-x")

        assert total == 1
        with open(arquivo, encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        assert len(linhas) == 1
        linha = linhas[0]
        # as colunas que o pipeline consome, com os valores mapeados
        assert linha["title"] == "Estética Vitá"
        assert linha["category"] == "Clínica de estética"
        assert linha["place_id"] == "ChIJabc123"
        assert linha["review_rating"] == "4.9"
        assert linha["review_count"] == "120"
        assert linha["phone"] == "(65) 3322-1122"
        assert linha["input_id"]  # uuid gerado por query

    def test_linha_qualifica_aceita_a_linha_gerada(self, tmp_path, monkeypatch):
        # integração real com o pipeline: a linha escrita passa no filtro de nota
        monkeypatch.setattr(
            fontes_maps.requests, "post",
            lambda *a, **kw: RespostaFake(200, {"places": [_place(nota=4.9)]}),
        )
        arquivo = tmp_path / "bruto.csv"
        fontes_maps.buscar_com_places_api(["barbearia em Cuiabá"], arquivo, "chave-x")
        with open(arquivo, encoding="utf-8") as f:
            linha = next(csv.DictReader(f))
        assert processar.linha_qualifica(linha) is True

    def test_input_id_distinto_por_query_preserva_mapeamento(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            fontes_maps.requests, "post",
            lambda *a, **kw: RespostaFake(200, {"places": [_place()]}),
        )
        arquivo = tmp_path / "bruto.csv"
        queries = ["barbearia em Cuiabá", "pet shop em Cuiabá"]
        fontes_maps.buscar_com_places_api(queries, arquivo, "chave-x")

        with open(arquivo, encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        assert len(linhas) == 2
        assert linhas[0]["input_id"] != linhas[1]["input_id"]

        # o mapeamento query→input_id do pipeline associa pela ordem
        mapeado = processar.mapear_queries_por_input_id(arquivo, self._queries_txt(tmp_path, queries))
        assert mapeado[linhas[0]["input_id"]] == "barbearia em Cuiabá"
        assert mapeado[linhas[1]["input_id"]] == "pet shop em Cuiabá"

    @staticmethod
    def _queries_txt(tmp_path, queries):
        caminho = tmp_path / "queries.txt"
        caminho.write_text("\n".join(queries) + "\n", encoding="utf-8")
        return caminho

    def test_paginacao_segue_next_page_token(self, tmp_path, monkeypatch):
        chamadas = []

        def post_fake(url, json=None, **kw):
            chamadas.append(json)
            if json.get("pageToken"):
                return RespostaFake(200, {"places": [_place(place_id="pagina2")]})
            return RespostaFake(200, {"places": [_place(place_id="pagina1")], "nextPageToken": "tok"})

        monkeypatch.setattr(fontes_maps.requests, "post", post_fake)
        arquivo = tmp_path / "bruto.csv"
        total = fontes_maps.buscar_com_places_api(["x"], arquivo, "chave")
        assert total == 2
        assert chamadas[1]["pageToken"] == "tok"

    def test_modo_mapa_envia_location_bias_circular(self, tmp_path, monkeypatch):
        corpos = []
        monkeypatch.setattr(
            fontes_maps.requests, "post",
            lambda url, json=None, **kw: (corpos.append(json), RespostaFake(200, {"places": []}))[1],
        )
        fontes_maps.buscar_com_places_api(
            ["barbearia"], tmp_path / "b.csv", "chave",
            area={"lat": -15.6, "lng": -56.1, "raio_m": 5000},
        )
        circulo = corpos[0]["locationBias"]["circle"]
        assert circulo["center"] == {"latitude": -15.6, "longitude": -56.1}
        assert circulo["radius"] == 5000.0

    def test_chave_recusada_vira_mensagem_amigavel(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            fontes_maps.requests, "post", lambda *a, **kw: RespostaFake(403, {})
        )
        with pytest.raises(fontes_maps.ErroPlacesApi, match="recusada"):
            fontes_maps.buscar_com_places_api(["x"], tmp_path / "b.csv", "chave-ruim")

    def test_cota_esgotada_vira_mensagem_amigavel(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            fontes_maps.requests, "post", lambda *a, **kw: RespostaFake(429, {})
        )
        with pytest.raises(fontes_maps.ErroPlacesApi, match="cota"):
            fontes_maps.buscar_com_places_api(["x"], tmp_path / "b.csv", "chave")


class TestValidarChavePlaces:
    def test_chave_boa(self, monkeypatch):
        monkeypatch.setattr(
            fontes_maps.requests, "post", lambda *a, **kw: RespostaFake(200, {"places": []})
        )
        ok, erro = fontes_maps.validar_chave_places("chave-boa")
        assert ok is True
        assert erro is None

    def test_chave_ruim(self, monkeypatch):
        monkeypatch.setattr(
            fontes_maps.requests, "post", lambda *a, **kw: RespostaFake(401, {})
        )
        ok, erro = fontes_maps.validar_chave_places("chave-ruim")
        assert ok is False
        assert "recusada" in erro


# ---------------------------------------------------------------------------
# jobs._capturar_dados_brutos - o branch da fonte
# ---------------------------------------------------------------------------

@pytest.fixture
def banco(tmp_path, monkeypatch):
    caminho = tmp_path / "leads_teste.db"
    monkeypatch.setattr(db, "CAMINHO_BANCO", caminho)
    # cofre fake: a chave "places" é secreta e iria pro Windows Credential
    # Manager REAL - substituímos por um dict em memória (padrão do test_db)
    cofre = {}
    monkeypatch.setattr(db, "_keyring_obter", cofre.get)
    monkeypatch.setattr(db, "_keyring_salvar", lambda chave, valor: cofre.update({chave: valor}) or True)
    monkeypatch.setattr(db, "_keyring_apagar", lambda chave: cofre.pop(chave, None))
    conexao = sqlite3.connect(caminho)
    processar.preparar_banco(conexao)
    conexao.close()
    return caminho


class TestCapturarDadosBrutos:
    def test_fonte_places_sem_chave_da_erro_amigavel(self, banco, tmp_path, monkeypatch):
        monkeypatch.setattr(jobs, "DIR_DADOS", tmp_path)
        db.salvar_config("fonte_maps", "places")
        erro = jobs._capturar_dados_brutos(tmp_path / "b.csv", {})
        assert "nenhuma chave" in erro

    def test_fonte_places_usa_a_api_e_nao_o_scraper(self, banco, tmp_path, monkeypatch):
        monkeypatch.setattr(jobs, "DIR_DADOS", tmp_path)
        (tmp_path / "queries.txt").write_text("barbearia em Cuiabá\n", encoding="utf-8")
        db.salvar_config("fonte_maps", "places")
        monkeypatch.setattr(db, "obter_config", lambda chave, default=None: {
            "fonte_maps": "places", "places": "chave-x",
        }.get(chave, default))

        chamado = {}

        def buscar_fake(queries, arquivo, chave, area=None, callback_query=None):
            chamado["queries"] = queries
            chamado["chave"] = chave
            return 7

        monkeypatch.setattr(fontes_maps, "buscar_com_places_api", buscar_fake)
        monkeypatch.setattr(
            jobs, "_executar_scraper",
            lambda *a, **kw: pytest.fail("o scraper não deveria rodar com fonte places"),
        )

        erro = jobs._capturar_dados_brutos(tmp_path / "b.csv", {})
        assert erro is None
        assert chamado["queries"] == ["barbearia em Cuiabá"]
        assert chamado["chave"] == "chave-x"
        assert jobs.estado_busca["empresas_encontradas"] >= 7

    def test_fonte_padrao_continua_no_scraper(self, banco, tmp_path, monkeypatch):
        # sem fonte_maps configurada, o comportamento é o de sempre
        chamado = {}
        monkeypatch.setattr(
            jobs, "_executar_scraper",
            lambda arquivo, ambiente, flags=(): chamado.setdefault("flags", flags),
        )
        jobs._capturar_dados_brutos(tmp_path / "b.csv", {}, area={"lat": -1.0, "lng": -2.0, "raio_m": 1000})
        assert "-geo" in chamado["flags"]


# ---------------------------------------------------------------------------
# Rotas: fonte-maps e login do Instagram
# ---------------------------------------------------------------------------

@pytest.fixture
def cliente(banco):
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


class TestRotaFonteMaps:
    def test_get_padrao_scraper(self, cliente):
        resposta = cliente.get("/api/configuracoes/fonte-maps")
        dados = resposta.get_json()
        assert resposta.status_code == 200
        assert dados["fonte"] == "scraper"
        assert dados["chave_configurada"] is False

    def test_post_fonte_invalida(self, cliente):
        resposta = cliente.post("/api/configuracoes/fonte-maps", json={"fonte": "banana"})
        assert resposta.status_code == 400

    def test_post_places_sem_chave(self, cliente):
        resposta = cliente.post("/api/configuracoes/fonte-maps", json={"fonte": "places"})
        assert resposta.status_code == 400
        assert "chave" in resposta.get_json()["erro"]

    def test_post_places_valida_e_salva(self, cliente, monkeypatch):
        monkeypatch.setattr(fontes_maps, "validar_chave_places", lambda chave: (True, None))
        resposta = cliente.post(
            "/api/configuracoes/fonte-maps", json={"fonte": "places", "chave": "chave-valida"}
        )
        dados = resposta.get_json()
        assert resposta.status_code == 200
        assert dados["fonte"] == "places"
        assert dados["chave_configurada"] is True
        assert db.obter_config("fonte_maps") == "places"

    def test_post_places_chave_invalida_nao_salva(self, cliente, monkeypatch):
        monkeypatch.setattr(
            fontes_maps, "validar_chave_places", lambda chave: (False, "chave recusada")
        )
        resposta = cliente.post(
            "/api/configuracoes/fonte-maps", json={"fonte": "places", "chave": "ruim"}
        )
        assert resposta.status_code == 400
        assert db.obter_config("fonte_maps") != "places"

    def test_post_volta_pro_scraper_sem_validar(self, cliente, monkeypatch):
        monkeypatch.setattr(
            fontes_maps, "validar_chave_places",
            lambda chave: pytest.fail("não deve validar chave ao voltar pro scraper"),
        )
        resposta = cliente.post("/api/configuracoes/fonte-maps", json={"fonte": "scraper"})
        assert resposta.status_code == 200


class TestRotasSessaoInstagram:
    @pytest.fixture
    def pasta_dados(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "DIR_DADOS", tmp_path)
        return tmp_path

    def test_sessao_inexistente(self, cliente, pasta_dados):
        dados = cliente.get("/api/instagram/sessao").get_json()
        assert dados == {"logada": False, "usuario": None}

    def test_sessao_existente_expoe_usuario(self, cliente, pasta_dados):
        pasta = pasta_dados / "instagram" / "sessao"
        pasta.mkdir(parents=True)
        (pasta / "session-nando.json").write_text("{}", encoding="utf-8")
        dados = cliente.get("/api/instagram/sessao").get_json()
        assert dados == {"logada": True, "usuario": "nando"}

    def test_delete_encerra_sessao(self, cliente, pasta_dados):
        pasta = pasta_dados / "instagram" / "sessao"
        pasta.mkdir(parents=True)
        (pasta / "session-nando.json").write_text("{}", encoding="utf-8")
        assert cliente.delete("/api/instagram/sessao").status_code == 200
        assert list(pasta.glob("session-*.json")) == []

    # ---- login com instagrapi fake ----

    @pytest.fixture
    def instagrapi_fake(self, monkeypatch):
        """Substitui o pacote instagrapi por um fake controlável."""
        class Fake2FA(Exception):
            pass

        estado = {"exigir_2fa": False, "falhar": None, "logins": []}

        class ClienteFake:
            def login(self, usuario, senha, verification_code=None):
                estado["logins"].append({"usuario": usuario, "codigo": verification_code})
                if estado["falhar"]:
                    raise Exception(estado["falhar"])
                if estado["exigir_2fa"] and not verification_code:
                    raise Fake2FA()

            def dump_settings(self, caminho):
                Path(caminho).write_text('{"sessao": "fake"}', encoding="utf-8")

        modulo = types.ModuleType("instagrapi")
        modulo.Client = ClienteFake
        excecoes = types.ModuleType("instagrapi.exceptions")
        excecoes.TwoFactorRequired = Fake2FA
        monkeypatch.setitem(sys.modules, "instagrapi", modulo)
        monkeypatch.setitem(sys.modules, "instagrapi.exceptions", excecoes)
        return estado

    def test_login_sem_credenciais(self, cliente, pasta_dados, instagrapi_fake):
        assert cliente.post("/api/instagram/login", json={}).status_code == 400

    def test_login_com_sucesso_salva_sessao(self, cliente, pasta_dados, instagrapi_fake):
        resposta = cliente.post(
            "/api/instagram/login", json={"usuario": "@nando", "senha": "s3nh4"}
        )
        dados = resposta.get_json()
        assert resposta.status_code == 200
        assert dados == {"ok": True, "usuario": "nando"}  # @ removido
        assert (pasta_dados / "instagram" / "sessao" / "session-nando.json").exists()

    def test_login_que_exige_2fa(self, cliente, pasta_dados, instagrapi_fake):
        instagrapi_fake["exigir_2fa"] = True
        resposta = cliente.post(
            "/api/instagram/login", json={"usuario": "nando", "senha": "s3nh4"}
        )
        assert resposta.get_json() == {"precisa_2fa": True}
        # nada salvo ainda
        assert not (pasta_dados / "instagram" / "sessao").exists()

        # reenvio com o código completa o login
        resposta = cliente.post(
            "/api/instagram/login",
            json={"usuario": "nando", "senha": "s3nh4", "codigo_2fa": "123456"},
        )
        assert resposta.get_json()["ok"] is True
        assert instagrapi_fake["logins"][-1]["codigo"] == "123456"

    def test_login_recusado(self, cliente, pasta_dados, instagrapi_fake):
        instagrapi_fake["falhar"] = "Senha incorreta"
        resposta = cliente.post(
            "/api/instagram/login", json={"usuario": "nando", "senha": "errada"}
        )
        assert resposta.status_code == 400
        assert "recusou" in resposta.get_json()["erro"]

    def test_login_novo_substitui_sessao_antiga(self, cliente, pasta_dados, instagrapi_fake):
        pasta = pasta_dados / "instagram" / "sessao"
        pasta.mkdir(parents=True)
        (pasta / "session-antigo.json").write_text("{}", encoding="utf-8")
        cliente.post("/api/instagram/login", json={"usuario": "novo", "senha": "x"})
        arquivos = [a.name for a in pasta.glob("session-*.json")]
        assert arquivos == ["session-novo.json"]