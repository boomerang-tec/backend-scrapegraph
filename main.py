import os
import re
import urllib.parse
import subprocess
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from scrapegraphai.graphs import SmartScraperGraph
from dotenv import load_dotenv

load_dotenv()

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    url: str
    prompt: str

@app.get("/")
def home():
    return {"message": "API ScrapeGraphAI Online com Logs e Busca Direta"}

def buscar_urls_gratuitas(termo: str) -> list:
    print(f"--> [ESTÁGIO 1] Iniciando busca por: {termo}")
    targets = []
    dominios_ignorados = [
        "google.", "instagram.com", "facebook.com", "linkedin.com",
        "youtube.com", "wikipedia.org", "duckduckgo.com", "twitter.com",
        "x.com", "pinterest.com", "tiktok.com", "tripadvisor.com",
        "yellowpages.com", "guiamais.com.br", "apontador.com.br"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        # Busca no HTML público do DuckDuckGo Lite (sem JS, rápido e sem bloqueio)
        query_encoded = urllib.parse.quote_plus(termo)
        search_url = f"https://lite.duckduckgo.com/lite/"
        response = requests.post(search_url, data={"q": termo}, headers=headers, timeout=10)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            links = soup.find_all("a", href=True)
            for link in links:
                href = link["href"]
                # Filtra links válidos
                if href.startswith("http") and not any(d in href for d in dominios_ignorados):
                    if href not in targets:
                        targets.append(href)
                        print(f"   [Site Encontrado]: {href}")
                if len(targets) >= 3:
                    break

        # Fallback de emergência se o filtro anterior não trouxer resultados
        if not targets:
            print("   [Aviso]: Busca secundária via Bing Lite...")
            bing_url = f"https://www.bing.com/search?q={query_encoded}"
            resp_bing = requests.get(bing_url, headers=headers, timeout=10)
            if resp_bing.status_code == 200:
                soup_bing = BeautifulSoup(resp_bing.text, "html.parser")
                for h2 in soup_bing.find_all("h2"):
                    a_tag = h2.find("a", href=True)
                    if a_tag:
                        href = a_tag["href"]
                        if href.startswith("http") and not any(d in href for d in dominios_ignorados):
                            if href not in targets:
                                targets.append(href)
                                print(f"   [Site Encontrado Bing]: {href}")
                        if len(targets) >= 3:
                            break

    except Exception as err:
        print(f"--> [ERRO ESTÁGIO 1]: {str(err)}")

    print(f"--> [ESTÁGIO 1 FINALIADO] Total de alvos encontrados: {len(targets)}")
    return targets

@app.post("/scrape")
def scrape_site(request: ScrapeRequest):
    print(f"\n================ Nova Requisição RECEBIDA ================")
    print(f"Entrada recebida: {request.url}")
    
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("--> [ERRO]: OPENAI_API_KEY ausente!")
        raise HTTPException(status_code=500, detail="Chave OPENAI_API_KEY não configurada no servidor.")

    targets = []

    # ETAPA 1: Identifica se é termo de busca ou URL direta
    if not request.url.startswith("http://") and not request.url.startswith("https://"):
        targets = buscar_urls_gratuitas(request.url)
    else:
        targets.append(request.url)

    if not targets:
        print("--> [FALHA]: Nenhum alvo válido encontrado. Retornando 404.")
        raise HTTPException(status_code=404, detail="Nenhum site oficial foi localizado para este termo. Tente refinar a busca com nome de bairro ou cidade.")

    # ETAPA 2: Processamento via ScrapeGraphAI nos sites encontrados
    all_leads = []

    prompt_detalhado = (
        f"{request.prompt}\n\n"
        "Analise o site corporativo e extraia no formato JSON:\n"
        "- nome_empresa: Nome oficial da empresa\n"
        "- telefone: Número de telefone fixo, celular ou WhatsApp com DDD\n"
        "- email: E-mail de contato encontrado na página\n"
        "- endereco: Endereço completo (rua, bairro, cidade, estado)\n"
        "- responsavel: Nome de sócio, gestor ou contato mencionado\n"
        "- website: A URL do próprio site analisado\n"
        "Retorne APENAS um JSON com esses campos."
    )

    graph_config = {
        "llm": {
            "api_key": openai_key,
            "model": "gpt-4o-mini",
        },
        "verbose": True,
        "headless": True,
    }

    print(f"--> [ESTÁGIO 2] Iniciando raspagem de {len(targets)} site(s) com ScrapeGraphAI...")

    for idx, site_url in enumerate(targets, 1):
        print(f"   [{idx}/{len(targets)}] Raspando: {site_url}")
        try:
            smart_scraper = SmartScraperGraph(
                prompt=prompt_detalhado,
                source=site_url,
                config=graph_config
            )
            result = smart_scraper.run()
            if result and isinstance(result, dict):
                result["website"] = site_url
                all_leads.append(result)
                print(f"   [Sucesso] Dados extraídos do site: {site_url}")
        except Exception as e:
            print(f"   [Erro ao raspar {site_url}]: {str(e)}")
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
                print("   [Tentando reinstalar Chromium via sub-processo...]")
                subprocess.run(["playwright", "install", "chromium"], check=True)
                smart_scraper = SmartScraperGraph(
                    prompt=prompt_detalhado,
                    source=site_url,
                    config=graph_config
                )
                result = smart_scraper.run()
                if result and isinstance(result, dict):
                    result["website"] = site_url
                    all_leads.append(result)

    print(f"================ Processamento CONCLUÍDO. Leads extraídos: {len(all_leads)} ================\n")
    return {"success": True, "total": len(all_leads), "leads": all_leads}
