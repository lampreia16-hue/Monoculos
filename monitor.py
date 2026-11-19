import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

# ================= CONFIGURAÇÕES =================
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

PRECO_MINIMO = 200
FICHEIRO_VISTOS = "anuncios_vistos.json"

# Pesquisas adaptadas ao idioma de cada plataforma
PESQUISAS_POR_PLATAFORMA = {
    "olx": ["hikmicro", "thermtec", "shotkam", "monoculo termico"],
    "wallapop": ["hikmicro", "thermtec", "shotkam", "monocular termico"],
    "vinted": ["hikmicro", "thermtec", "shotkam", "monocular termico", "monoculaire thermique"],
    "kleinanzeigen": ["hikmicro", "thermtec", "shotkam", "waermebild-monokular"]
}

# O título do anúncio TEM de conter pelo menos uma destas expressões
PALAVRAS_OBRIGATORIAS_TITULO = [
    # Hikmicro e ThermTec + modelos
    "hikmicro", "hik micro", "hik-micro",
    "thermtec", "therm tec", "therm-tec",
    "lh15", "lh19", "lh25", "lh35", "lq35", "lq50", "le10", "le15",
    "cq35", "cq50", "fq35", "fq50", "tq50", "gh35", "fh35",
    "habrok", "wild 335", "wild 350", "wild 650", "cyclops",
    # ShotKam
    "shotkam", "shot kam", "shot-kam",
    # Monóculos térmicos genéricos (PT / ES / FR / IT / DE / EN)
    "monóculo térmico", "monoculo termico",
    "monocular térmico", "monocular termico",
    "monoculaire thermique", "visore termico",
    "wärmebild", "waermebild", "thermal monocular",
    "visão térmica", "visao termica"
]

# Ignora "procura-se", câmaras industriais/obras e anúncios típicos de lojas alemãs
PALAVRAS_IGNORAR = [
    "suche", "gesuch", "compro", "procuro",
    "pocket", "b10s", "b20", "heatpro", "e1l",
    "flir", "bosch", "testo", "uni-t", "topdon", "seek", "milwaukee", "makita", "hilti",
    "black deal", "vorführgerät", "bestpreis"
]
# =================================================

HEADERS_WALLAPOP = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-DeviceOS": "0",
    "Accept": "application/json"
}


def titulo_valido(titulo):
    texto = titulo.lower()
    if any(p in texto for p in PALAVRAS_IGNORAR):
        return False
    return any(p in texto for p in PALAVRAS_OBRIGATORIAS_TITULO)


def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"[Erro Telegram] {r.status_code} -> {r.text}")
    except Exception as e:
        print(f"[Erro Telegram] {e}")


def carregar_vistos():
    if os.path.exists(FICHEIRO_VISTOS):
        with open(FICHEIRO_VISTOS, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def guardar_vistos(vistos):
    with open(FICHEIRO_VISTOS, "w", encoding="utf-8") as f:
        json.dump(sorted(list(vistos)), f, indent=2)


def pesquisar_olx(termo):
    resultados = []
    url = "https://www.olx.pt/api/v1/offers/"
    params = {"query": termo, "sort_by": "created_at:desc", "limit": 20}
    try:
        r = cffi_requests.get(url, params=params, impersonate="chrome", timeout=15)
        if r.status_code != 200:
            print(f"[OLX] Estado {r.status_code} para '{termo}'")
            return resultados

        for item in r.json().get("data", []):
            titulo = item.get("title", "Sem título")
            if not titulo_valido(titulo):
                continue

            preco = 0
            for p in item.get("params", []):
                if p.get("key") == "price":
                    preco = p.get("value", {}).get("value", 0) or 0
                    break

            if preco >= PRECO_MINIMO:
                resultados.append({
                    "id": f"olx_{item['id']}",
                    "plataforma": "OLX PT",
                    "titulo": titulo,
                    "preco": f"{preco:.0f} €",
                    "link": item.get("url", "")
                })
    except Exception as e:
        print(f"[Erro OLX '{termo}'] {e}")
    return resultados


def pesquisar_wallapop(termo):
    resultados = []
    url = "https://api.wallapop.com/api/v3/search"
    params = {
        "source": "search_box",
        "keywords": termo,
        "order_by": "newest",
        "min_sale_price": PRECO_MINIMO,
        "latitude": 39.5,
        "longitude": -4.5,
        "distance_in_km": 1000
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS_WALLAPOP, timeout=15)
        if r.status_code != 200:
            print(f"[Wallapop] Estado {r.status_code} para '{termo}'")
            return resultados

        dados = r.json()
        itens = dados.get("search_objects") or dados.get("data", {}).get("section", {}).get("payload", {}).get("items", [])

        for item in itens:
            titulo = item.get("title", "Sem título")
            if not titulo_valido(titulo):
                continue

            item_id = item.get("id")
            slug = item.get("web_slug", "")
            preco_raw = item.get("price", 0)
            preco_val = preco_raw.get("amount", 0) if isinstance(preco_raw, dict) else (preco_raw or 0)

            if item_id and preco_val >= PRECO_MINIMO:
                resultados.append({
                    "id": f"wallapop_{item_id}",
                    "plataforma": "Wallapop",
                    "titulo": titulo,
                    "preco": f"{preco_val:.0f} €",
                    "link": f"https://es.wallapop.com/item/{slug}" if slug else "https://es.wallapop.com"
                })
    except Exception as e:
        print(f"[Erro Wallapop '{termo}'] {e}")
    return resultados


def pesquisar_vinted(termo):
    resultados = []
    url = "https://www.vinted.pt/catalog"
    params = {
        "search_text": termo,
        "order": "newest_first",
        "price_from": PRECO_MINIMO
    }
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"
    }
    try:
        r = cffi_requests.get(url, params=params, headers=headers, impersonate="chrome", timeout=15)
        if r.status_code != 200:
            print(f"[Vinted] Estado {r.status_code} para '{termo}'")
            return resultados

        soup = BeautifulSoup(r.text, "html.parser")
        vistos_locais = set()
        for a in soup.select('a[href*="/items/"]'):
            href = a.get("href", "")
            match = re.search(r"/items/(\d+)", href)
            if not match:
                continue
            item_id = match.group(1)
            if item_id in vistos_locais:
                continue
            vistos_locais.add(item_id)

            texto_completo = a.get("title") or a.get_text(" ", strip=True)
            if not texto_completo or not titulo_valido(texto_completo):
                continue

            titulo_limpo = re.split(r",\s*(?:Marca|Estado):", texto_completo, maxsplit=1)[0].strip()
            match_preco = re.search(r"(\d+(?:\.\d{3})*)[.,]\d{2}\s*€", texto_completo)
            preco_val = int(match_preco.group(1).replace(".", "")) if match_preco else 0

            if preco_val >= PRECO_MINIMO or preco_val == 0:
                link_final = href if href.startswith("http") else f"https://www.vinted.pt{href}"
                resultados.append({
                    "id": f"vinted_{item_id}",
                    "plataforma": "Vinted",
                    "titulo": titulo_limpo[:120],
                    "preco": f"{preco_val} €" if preco_val else "Ver no anúncio",
                    "link": link_final
                })
    except Exception as e:
        print(f"[Erro Vinted '{termo}'] {e}")
    return resultados


def pesquisar_kleinanzeigen(termo):
    resultados = []
    termo_url = termo.replace(" ", "-")
    url = f"https://www.kleinanzeigen.de/s-{termo_url}/k0"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"
    }
    try:
        r = cffi_requests.get(url, headers=headers, impersonate="chrome", timeout=15)
        if r.status_code != 200:
            print(f"[Kleinanzeigen] Estado {r.status_code} para '{termo}'")
            return resultados

        soup = BeautifulSoup(r.text, "html.parser")
        vistos_locais = set()
        for a in soup.select('a[href*="/s-anzeige/"]'):
            href = a.get("href", "")
            titulo = a.get_text(" ", strip=True)
            if not titulo or len(titulo) < 5:
                continue

            match_id = re.search(r"/(\d+)-\d+-\d+", href)
            if not match_id:
                continue
            ad_id = match_id.group(1)
            if ad_id in vistos_locais:
                continue
            vistos_locais.add(ad_id)

            if not titulo_valido(titulo):
                continue

            bloco = a.find_parent(["article", "li"]) or a.parent
            texto_bloco = bloco.get_text(" ", strip=True) if bloco else ""
            match_preco = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+)\s*€", texto_bloco)
            preco_val = int(match_preco.group(1).replace(".", "")) if match_preco else 0

            if preco_val >= PRECO_MINIMO:
                link_final = href if href.startswith("http") else f"https://www.kleinanzeigen.de{href}"
                resultados.append({
                    "id": f"kleinanzeigen_{ad_id}",
                    "plataforma": "Kleinanzeigen",
                    "titulo": titulo,
                    "preco": f"{preco_val} €",
                    "link": link_final
                })
    except Exception as e:
        print(f"[Erro Kleinanzeigen '{termo}'] {e}")
    return resultados


def executar_ciclo():
    vistos = carregar_vistos()
    primeira_vez = len(vistos) == 0
    novos = []

    funcoes = {
        "olx": pesquisar_olx,
        "wallapop": pesquisar_wallapop,
        "vinted": pesquisar_vinted,
        "kleinanzeigen": pesquisar_kleinanzeigen
    }

    for plataforma, termos in PESQUISAS_POR_PLATAFORMA.items():
        func = funcoes[plataforma]
        for termo in termos:
            for a in func(termo):
                if a["id"] not in vistos:
                    vistos.add(a["id"])
                    novos.append(a)
            time.sleep(2)

    guardar_vistos(vistos)

    if primeira_vez:
        enviar_telegram(
            f"✅ <b>Monitor 24/7 atualizado!</b>\n"
            f"Base criada com {len(vistos)} anúncios (Térmicos + ShotKam).\n"
            f"A partir de agora só recebes alertas de novidades."
        )
        print(f"Base inicial criada com {len(vistos)} anúncios.")
    else:
        for a in novos:
            msg = (
                f"🔥 <b>Novo anúncio no {a['plataforma']}</b>\n"
                f"📌 {a['titulo']}\n"
                f"💶 <b>{a['preco']}</b>\n"
                f"🔗 {a['link']}"
            )
            enviar_telegram(msg)
            print(f"[NOVO] {a['plataforma']} | {a['titulo']} ({a['preco']})")
            time.sleep(1)
        print(f"Ciclo concluído. Novos anúncios: {len(novos)}.")


if __name__ == "__main__":
    executar_ciclo()
