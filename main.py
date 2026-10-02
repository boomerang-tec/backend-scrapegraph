import os
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
    return {"message": "API ScrapeGraphAI Online - Logs Ativos"}

def buscar_urls_gratuitas(termo: str) -> list:
    print(f"\n[ESTAGIO 1] Iniciando busca para o termo: '{termo}'", flush=True)
    targets = []
    dominios_ignorados = [
        "google.", "instagram.com", "facebook.com", "linkedin.com",
        "youtube.com", "wikipedia.org", "duckduckgo.com", "twitter.com",
        "x.com", "pinterest.com", "tiktok.com", "tripadvisor.com",
        "yellowpages.com", "guiamais.com.br", "apontador.com.br"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        query_encoded = urllib.parse.quote_plus(f"{termo} site oficial")
        url_busca = f"https://html.duckduckgo.com/html/?q={query_encoded}"
        
        print(f"[ESTAGIO 1] Requisitando: {url_busca}", flush=True)
        resp = requests.get(url_busca, headers=headers, timeout=12)
        
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            links = soup.find_all("a", class_="result__url")
            
            for link in links:
                href = link.get("href", "")
                if "uddg=" in href:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    real_url = parsed.get("uddg", [""])[0]
                else:
                    real_url = href

                if real_url and real_url.startswith("http") and not any(d in real_url for d in dominios_ignorados):
                    if real_url not in targets:
                        targets.append(real_url)
                        print(f"   -> Site oficial encontrado: {real_url}", flush=True)
                
                if len(targets) >= 3:
                    break

    except Exception as err:
        print(f"[ERRO ESTAGIO 1]: {str(err)}", flush=True)

    print(f"[ESTAGIO 1 FINALIADO] Total de URLs capturadas: {len(targets)}", flush=True)
    return targets

@app.post("/scrape")
def scrape_site(request: ScrapeRequest):
    print(f"\n================ NOVA REQUISICAO /SCRAPE ================", flush=True)
    print(f"Entrada informada pelo cliente: '{request.url}'", flush=True)
    
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("[ERRO CRITICO]: OPENAI_API_KEY ausente nas variaveis de ambiente!", flush=True)
        raise HTTPException(status_code=500, detail="Chave OPENAI_API_KEY não configurada no servidor.")

    targets = []

    if not request.url.startswith("http://") and not request.url.startswith("https://"):
        targets = buscar_urls_gratuitas(request.url)
    else:
        targets.append(request.url)

    if not targets:
        print("[FALHA]: Nenhuma URL valida capturada. Retornando 404.", flush=True)
        raise HTTPException(status_code=404, detail="Nenhum site oficial foi encontrado para o termo pesquisado.")

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

    print(f"[ESTAGIO 2] Processando {len(targets)} site(s) com ScrapeGraphAI...", flush=True)

    for idx, site_url in enumerate(targets, 1):
        print(f"   [{idx}/{len(targets)}] Extraindo dados de: {site_url}", flush=True)
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
                print(f"   [SUCESSO]: Dados raspados com sucesso de {site_url}", flush=True)
        except Exception as e:
            print(f"   [ERRO ao raspar {site_url}]: {str(e)}", flush=True)
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
                print("   [Instalando Chromium via sub-processo...]", flush=True)
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

    print(f"================ REQUISICAO FINALIZADA (Leads: {len(all_leads)}) ================\n", flush=True)
    return {"success": True, "total": len(all_leads), "leads": all_leads}
