import os
import subprocess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from scrapegraphai.graphs import SmartScraperGraph
from playwright.sync_api import sync_playwright
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
    return {"message": "API ScrapeGraphAI Online (100% Gratuita via Playwright)"}

def buscar_urls_com_playwright(termo: str) -> list:
    targets = []
    dominios_ignorados = [
        "google.com", "instagram.com", "facebook.com", "linkedin.com",
        "youtube.com", "wikipedia.org", "duckduckgo.com", "twitter.com",
        "x.com", "pinterest.com", "tiktok.com", "tripadvisor.com"
    ]
    
    query = termo.replace(" ", "+")
    search_url = f"https://html.duckduckgo.com/html/?q={query}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        
        # Seleciona os links dos resultados orgânicos do DuckDuckGo HTML
        links = page.locator("a.result__url").all()
        
        for link_elem in links:
            href = link_elem.get_attribute("href")
            if href:
                # O DuckDuckGo HTML encapsula o link real no parâmetro 'uddg'
                if "uddg=" in href:
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    real_url = parsed.get("uddg", [""])[0]
                else:
                    real_url = href
                
                if real_url and real_url.startswith("http") and not any(d in real_url for d in dominios_ignorados):
                    if real_url not in targets:
                        targets.append(real_url)
                
                if len(targets) >= 3:
                    break
        
        browser.close()

    return targets

@app.post("/scrape")
def scrape_site(request: ScrapeRequest):
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(status_code=500, detail="Chave OPENAI_API_KEY não configurada no servidor.")

    targets = []

    # ETAPA 1: Se for um termo de busca (sem http/https), busca as URLs reais usando Playwright
    if not request.url.startswith("http://") and not request.url.startswith("https://"):
        try:
            targets = buscar_urls_com_playwright(request.url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro na busca Playwright: {str(e)}")
    else:
        targets.append(request.url)

    if not targets:
        raise HTTPException(status_code=404, detail="Nenhum site oficial foi encontrado para o termo informado.")

    # ETAPA 2: Processamento e raspagem no ScrapeGraphAI
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

    for site_url in targets:
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
        except Exception as e:
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
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

    return {"success": True, "total": len(all_leads), "leads": all_leads}
