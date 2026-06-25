# -*- coding: utf-8 -*-
"""
api_client.py — GeoCAR Suite
API SEMAS-PA: buscarCAR · buscarGeojson · baixarDemonstrativo

Autenticação via Selenium + Chrome DevTools Protocol (CDP):
  - Chrome abre minimizado (visível ao SO, mas sem incomodar o usuário)
  - CDP monitora TODAS as requisições de rede em tempo real
  - Bearer token é capturado da primeira requisição autenticada
  - Cache de sessão evita re-autenticação desnecessária
"""

import re as _re
import time
import json as _json
import logging
import requests

log = logging.getLogger("GeoCAR_Suite")

BASE               = "https://portal-servicos-sistemas.semas.pa.gov.br"
URL_PORTAL         = BASE + "/consulta-mapa"
URL_BUSCAR_CAR     = (BASE + "/api/1/servicedesk-embedded-servicos-sistemas"
                      "/_classId/649086b520338013be9c0e2d/buscarCAR")
URL_BUSCAR_GEOJSON = (BASE + "/api/1/servicedesk-embedded-servicos-sistemas"
                      "/_classId/65689c680c1eb452fcd3d01b"
                      "/consultaBuscarGeojsonDaAreaDoImovel")
URL_DEMONSTRATIVO  = (BASE + "/api/1/servicedesk-embedded-servicos-sistemas"
                      "/_classId/649086b520338013be9c0e2d"
                      "/baixarVisualizarDemonstrativoDoCar")
URL_DOWNLOAD_ARQUIVO = (BASE + "/api/1/servicedesk-embedded-servicos-sistemas"
                        "/_classId/000000c819062a2fb5741d80/_download/{id1}/{id2}")

HEADERS_BASE = {
    "Content-Type":             "application/json",
    "Accept":                   "*/*",
    "Accept-Language":          "pt",
    "Origin":                   BASE,
    "Referer":                  URL_PORTAL,
    "x-explorer-account-token": "atos-autorizativos",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
    "sec-fetch-dest":  "empty",
    "sec-fetch-mode":  "cors",
    "sec-fetch-site":  "same-origin",
    "dnt":             "1",
}

_sessao_cache = {"token": None, "cookies": {}, "obtido_em": 0}
TOKEN_VALIDADE = 3600
_OBJECTID_RE   = _re.compile(r"^[a-f0-9]{24}$", _re.IGNORECASE)


# ─────────────────────────────────────────────────────────────
# SESSÃO
# ─────────────────────────────────────────────────────────────

def _token_valido():
    return (bool(_sessao_cache["token"]) and
            (time.time() - _sessao_cache["obtido_em"]) < TOKEN_VALIDADE)

def _headers_autenticados():
    h = dict(HEADERS_BASE)
    if _sessao_cache["token"]:
        h["authorization"] = f"Bearer {_sessao_cache['token']}"
    return h

def _criar_sessao():
    s = requests.Session()
    s.headers.update(_headers_autenticados())
    for nome, valor in _sessao_cache.get("cookies", {}).items():
        s.cookies.set(nome, valor)
    return s

def garantir_autenticacao(timeout=20):
    if _token_valido():
        return True, "Cache válido"
    return _autenticar(timeout)


# ─────────────────────────────────────────────────────────────
# AUTENTICAÇÃO — Chrome + CDP (método principal)
# ─────────────────────────────────────────────────────────────

def _autenticar(timeout=20):
    """
    Abre o Chrome minimizado e usa o Chrome DevTools Protocol (CDP)
    para interceptar as requisições de rede e capturar o Bearer token.

    O CDP é muito mais confiável que logs de performance porque monitora
    em tempo real e funciona com qualquer modo de janela.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
    except ImportError:
        return False, "Selenium não instalado. Execute: pip install selenium"

    log.info("  Iniciando autenticação SEMAS-PA via CDP...")

    opcoes = Options()

    # ── Modo minimizado (visível ao SO → Angular inicializa corretamente) ──
    opcoes.add_argument("--start-minimized")
    opcoes.add_argument("--no-sandbox")
    opcoes.add_argument("--disable-dev-shm-usage")
    opcoes.add_argument("--disable-blink-features=AutomationControlled")
    opcoes.add_argument("--disable-extensions")
    opcoes.add_argument("--disable-gpu")
    opcoes.add_experimental_option("excludeSwitches", ["enable-automation"])
    opcoes.add_experimental_option("useAutomationExtension", False)
    opcoes.add_argument(f"--user-agent={HEADERS_BASE['User-Agent']}")

    # ── Habilitar log de performance para captura de rede ──
    opcoes.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = None
    token  = None

    try:
        driver = webdriver.Chrome(options=opcoes)

        # Remover assinatura de automação
        driver.execute_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )

        # ── Habilitar CDP Network para captura em tempo real ──
        driver.execute_cdp_cmd("Network.enable", {})

        log.info(f"  Abrindo: {URL_PORTAL}")
        driver.get(URL_PORTAL)

        # ── Aguardar token aparecer (verifica a cada 1s por até timeout s) ──
        log.info("  Aguardando autenticação do portal...")
        inicio = time.time()

        while (time.time() - inicio) < timeout:
            time.sleep(1)

            # Verificar logs de performance em busca do token
            try:
                logs = driver.get_log("performance")
                for entrada in logs:
                    try:
                        msg = _json.loads(entrada["message"])["message"]
                        metodo = msg.get("method", "")

                        if metodo == "Network.requestWillBeSent":
                            req  = msg["params"].get("request", {})
                            url  = req.get("url", "")
                            hdrs = req.get("headers", {})
                            auth = hdrs.get("authorization", "") or hdrs.get("Authorization", "")

                            if ("semas.pa.gov.br" in url and
                                    auth.startswith("Bearer ")):
                                token = auth.replace("Bearer ", "").strip()
                                log.info(f"  ✓ Token capturado via CDP ({len(token)} chars)")
                                break
                    except Exception:
                        continue
                if token:
                    break
            except Exception as e:
                log.debug(f"  CDP log: {e}")

        # ── Fallback 1: localStorage / sessionStorage ──
        if not token:
            log.info("  Tentando storage...")
            scripts = [
                "return localStorage.getItem('token')",
                "return localStorage.getItem('access_token')",
                "return localStorage.getItem('authToken')",
                "return sessionStorage.getItem('token')",
                "return sessionStorage.getItem('access_token')",
                """
                var chaves = Object.keys(localStorage).concat(Object.keys(sessionStorage));
                for(var i=0;i<chaves.length;i++){
                    var v = localStorage.getItem(chaves[i]) || sessionStorage.getItem(chaves[i]);
                    if(v && v.length > 100 && chaves[i].toLowerCase().indexOf('token')>=0)
                        return v;
                }
                return null;
                """,
            ]
            for script in scripts:
                try:
                    r = driver.execute_script(script)
                    if r and len(str(r)) > 50:
                        token = str(r).replace("Bearer ", "").strip()
                        log.info("  ✓ Token capturado via storage")
                        break
                except Exception:
                    continue

        # ── Fallback 2: forçar requisição autenticada via JS ──
        if not token:
            log.info("  Forçando requisição autenticada...")
            try:
                # Usar fetch() do próprio navegador — o Angular injeta o token automaticamente
                driver.execute_script("""
                    window.__tokenCapturado = null;
                    var origFetch = window.fetch;
                    window.fetch = function(url, opts) {
                        if(opts && opts.headers) {
                            var auth = opts.headers['authorization'] || opts.headers['Authorization'];
                            if(auth && auth.indexOf('Bearer') >= 0) {
                                window.__tokenCapturado = auth.replace('Bearer ','').trim();
                            }
                        }
                        return origFetch.apply(this, arguments);
                    };
                """)

                # Disparar uma busca no portal para gerar uma requisição autenticada
                driver.execute_script("""
                    fetch('/api/1/servicedesk-embedded-servicos-sistemas/_classId/649086b520338013be9c0e2d/buscarCAR', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'x-explorer-account-token': 'atos-autorizativos'
                        },
                        body: JSON.stringify({
                            codigoCar: 'PA-0000000-00000000000000000000000000000000',
                            page: 0, itemsPerPage: 1, precisaRecibo: false,
                            municipio: '', nomeImovel: null,
                            cpfCadastrante: null, cpfCnpjProprietario: null,
                            protocolo: null
                        })
                    }).catch(function(){});
                """)

                time.sleep(4)

                # Tentar capturar o token interceptado
                t = driver.execute_script("return window.__tokenCapturado;")
                if t and len(str(t)) > 50:
                    token = str(t).strip()
                    log.info("  ✓ Token capturado via fetch interceptor")

                # Verificar logs novamente após o fetch
                if not token:
                    for entrada in driver.get_log("performance"):
                        try:
                            msg = _json.loads(entrada["message"])["message"]
                            if msg.get("method") == "Network.requestWillBeSent":
                                req  = msg["params"].get("request", {})
                                url  = req.get("url", "")
                                auth = (req.get("headers", {}).get("authorization", "") or
                                        req.get("headers", {}).get("Authorization", ""))
                                if "semas.pa.gov.br" in url and auth.startswith("Bearer "):
                                    token = auth.replace("Bearer ", "").strip()
                                    log.info("  ✓ Token capturado via log pós-fetch")
                                    break
                        except Exception:
                            continue

            except Exception as e:
                log.debug(f"  Fetch interceptor: {e}")

        # ── Capturar cookies (Cloudflare __cf_bm etc.) ──
        cookies = {}
        try:
            cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
            log.info(f"  {len(cookies)} cookie(s) capturado(s)")
        except Exception as e:
            log.debug(f"  Cookies: {e}")

        # ── Salvar em cache ──
        if token:
            _sessao_cache.update({
                "token":     token,
                "cookies":   cookies,
                "obtido_em": time.time(),
            })
            log.info("  ✓ Autenticação concluída com sucesso")
            return True, "OK"

        if cookies:
            _sessao_cache.update({"cookies": cookies, "obtido_em": time.time()})
            log.warning("  ⚠ Apenas cookies capturados (sem token Bearer)")
            return True, "Cookies capturados"

        # ── Diagnóstico detalhado ──
        return False, (
            "Token não encontrado após todas as estratégias.\n\n"
            "Possíveis causas:\n"
            "  1. Chrome não instalado ou versão incompatível com ChromeDriver\n"
            "  2. Portal SEMAS-PA inacessível (verifique conexão/VPN)\n"
            "  3. Portal alterou o mecanismo de autenticação\n\n"
            "Diagnóstico: abra manualmente o portal no Chrome,\n"
            "pressione F12 → Network → faça uma busca → copie o\n"
            "header 'authorization' e cole no chat."
        )

    except Exception as e:
        return False, (
            f"Erro ao iniciar o Chrome: {e}\n\n"
            "Verifique:\n"
            "  1. Google Chrome está instalado\n"
            "  2. ChromeDriver compatível: pip install webdriver-manager\n"
            "     e adicione ao script: from webdriver_manager.chrome import ChromeDriverManager\n"
            "                           from selenium.webdriver.chrome.service import Service\n"
            "                           driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))"
        )
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────
# ENDPOINT 1 — buscarCAR
# ─────────────────────────────────────────────────────────────

def buscar_id_car(codigo_car: str, timeout=30):
    ok, msg = garantir_autenticacao(timeout)
    if not ok:
        return False, f"Auth: {msg}"

    payload = {
        "codigoCar":           codigo_car.strip().upper(),
        "cpfCadastrante":      None,
        "cpfCnpjProprietario": None,
        "itemsPerPage":        7,
        "municipio":           "",
        "nomeImovel":          None,
        "page":                0,
        "precisaRecibo":       False,
        "protocolo":           None,
    }
    sessao = _criar_sessao()
    try:
        resp = sessao.post(URL_BUSCAR_CAR, json=payload, timeout=timeout)

        if resp.status_code in (401, 403):
            log.warning("  Token expirado — renovando...")
            _sessao_cache["token"] = None
            ok, msg = garantir_autenticacao(timeout)
            if not ok: return False, f"Renovação: {msg}"
            sessao = _criar_sessao()
            resp   = sessao.post(URL_BUSCAR_CAR, json=payload, timeout=timeout)

        resp.raise_for_status()
        dados = resp.json()
        log.info(f"  Resposta buscarCAR: {str(dados)[:200]}")

        items = dados.get("items") or dados.get("data") or []
        if isinstance(dados, list): items = dados
        if not items:
            for v in (dados.values() if isinstance(dados, dict) else []):
                if isinstance(v, list) and v:
                    items = v; break

        if not items:
            return False, f"Não encontrado (resp: {str(dados)[:150]})"

        id_car = None
        for item in items:
            if not isinstance(item, dict): continue
            cod = (item.get("codigoCar") or "").strip().upper()
            if cod == codigo_car.strip().upper() or not id_car:
                id_car = item.get("_id") or item.get("id") or item.get("idCar")

        if not id_car:
            return False, f"_id ausente. Estrutura: {str(items[0])[:150]}"

        log.info(f"  _id: {id_car}")
        return True, id_car

    except requests.exceptions.Timeout:    return False, f"Timeout ({timeout}s)"
    except requests.exceptions.ConnectionError: return False, "Sem conexão"
    except requests.exceptions.HTTPError as e:  return False, f"HTTP {resp.status_code}: {e}"
    except Exception as e:                 return False, str(e)


# ─────────────────────────────────────────────────────────────
# ENDPOINT 2 — buscarGeojson
# ─────────────────────────────────────────────────────────────

def buscar_geojson(id_car: str, timeout=30):
    sessao = _criar_sessao()
    try:
        resp = sessao.post(URL_BUSCAR_GEOJSON, json={"idCar": id_car}, timeout=timeout)
        resp.raise_for_status()
        dados   = resp.json()
        geojson = (dados.get("geoJson") or dados.get("geojson")
                   or dados.get("geometry") or dados)
        if not geojson or "geometry" not in geojson:
            return False, f"GeoJSON inválido: {str(dados)[:150]}"
        log.info(f"  GeoJSON: {geojson.get('geometry',{}).get('type')}")
        return True, geojson
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────
# ENDPOINT 3 — demonstrativo PDF
# ─────────────────────────────────────────────────────────────

def baixar_demonstrativo(id_car: str, timeout=60):
    ok, msg = garantir_autenticacao(timeout)
    if not ok: return False, f"Auth: {msg}"

    sessao = _criar_sessao()
    try:
        resp = sessao.post(
            URL_DEMONSTRATIVO,
            json={"idCar": id_car, "operacao": "download"},
            timeout=timeout
        )
        if resp.status_code in (401, 403):
            _sessao_cache["token"] = None
            ok, msg = garantir_autenticacao(timeout)
            if not ok: return False, f"Renovação: {msg}"
            sessao = _criar_sessao()
            resp   = sessao.post(
                URL_DEMONSTRATIVO,
                json={"idCar": id_car, "operacao": "download"},
                timeout=timeout
            )
        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "").lower()

        if "application/pdf" in ct or resp.content[:4] == b"%PDF":
            log.info(f"  PDF: {len(resp.content)/1024:.1f} KB")
            return True, resp.content

        if "application/json" in ct:
            import base64
            dados = resp.json()
            for campo in ["arquivo","base64","data","conteudo","pdf","file"]:
                valor = dados.get(campo) if isinstance(dados, dict) else None
                if valor and isinstance(valor, str) and len(valor) > 100:
                    s = valor.split(",",1)[1] if "," in valor[:50] else valor
                    try:
                        pdf = base64.b64decode(s)
                        if pdf[:4] == b"%PDF": return True, pdf
                    except Exception: pass
            ids = _coletar_object_ids(dados)
            if ids:
                log.info(f"  IDs encontrados: {ids}")
                return _baixar_por_ids(sessao, ids, timeout)
            return False, f"PDF não encontrado: {str(dados)[:200]}"

        return False, f"Formato inesperado: {ct}"

    except requests.exceptions.Timeout:       return False, f"Timeout ({timeout}s)"
    except requests.exceptions.ConnectionError: return False, "Sem conexão"
    except requests.exceptions.HTTPError as e:  return False, f"HTTP {resp.status_code}: {e}"
    except Exception as e:                     return False, str(e)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _coletar_object_ids(obj, encontrados=None):
    if encontrados is None: encontrados = []
    if isinstance(obj, dict):
        for v in obj.values(): _coletar_object_ids(v, encontrados)
    elif isinstance(obj, list):
        for item in obj: _coletar_object_ids(item, encontrados)
    elif isinstance(obj, str):
        if _OBJECTID_RE.match(obj) and obj not in encontrados:
            encontrados.append(obj)
    return encontrados


def _baixar_por_ids(sessao, ids, timeout, max_tent=8):
    erros = []; tent = 0
    for id1 in ids:
        for id2 in ids:
            if tent >= max_tent: break
            tent += 1
            url = URL_DOWNLOAD_ARQUIVO.format(id1=id1, id2=id2)
            try:
                r = sessao.get(url,
                               params={"contentType": "application/pdf; charset=utf-8"},
                               timeout=timeout)
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    log.info(f"  PDF via _download: {len(r.content)/1024:.1f} KB")
                    return True, r.content
                erros.append(f"{id1[:8]}/{id2[:8]}: HTTP {r.status_code}")
            except Exception as e: erros.append(str(e))
        if tent >= max_tent: break
    return False, (f"Nenhuma combinação retornou PDF ({tent} tentativas). "
                   f"Detalhes: {'; '.join(erros[:5])}")


# ─────────────────────────────────────────────────────────────
# CONVENIÊNCIA
# ─────────────────────────────────────────────────────────────

def buscar_imovel_completo(codigo_car: str, timeout=30):
    ok, id_car = buscar_id_car(codigo_car, timeout)
    if not ok: return False, id_car
    ok, geojson = buscar_geojson(id_car, timeout)
    if not ok: return False, geojson
    return True, {"id": id_car, "geojson": geojson, "codigo_car": codigo_car}
