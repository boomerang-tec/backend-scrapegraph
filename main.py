import os
import subprocess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from scrapegraphai.graphs import SmartScraperGraph
from ddgs import DDGS
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
    return {"message": "API ScrapeGraphAI Online (100% Gratuita)"}

def buscar_urls_gratuitas(termo: str) -> list:
    targets = []
    # Lista de domínios que não são sites diretos das empresas
    dominios_ignorados = [
        "google.com", "instagram.com", "facebook.com", "linkedin.com",
        "youtube.com", "wikipedia.org", "duckduckgo.com", "twitter.com",
        "x.com", "pinterest.com", "tiktok.com"
    ]
    
    # Fazemos a busca com regionalização para o Brasil (br-pt)
    with DDGS() as ddgs_client:
        # Busca 15 resultados para ter margem de filtro
        resultados = list(ddgs_client.text(f"{termo} contato", region="br-pt", max_results=15))
        
        for item in resultados:
            link = item.get("href", "")
            if link and not any(domain in link for domain in dominios_ignorados):
                targets.append(link)
            if len(targets) >= 3:
                break
                
    return targets

@app.post("/scrape")
def scrape_site(request: ScrapeRequest):
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(status_code=500, detail="Chave OPENAI_API_KEY não configurada.")

    targets = []

    # ETAPA 1: Identificar se é uma URL direta ou termo de busca
    if not request.url.startswith("http://") and not request.url.startswith("https://"):
        try:
            targets = buscar_urls_gratuitas(request.url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao buscar sites no DuckDuckGo: {str(e)}")
    else:
        targets.append(request.url)

    if not targets:
        raise HTTPException(status_code=404, detail="Nenhum site oficial foi encontrado para o termo pesquisado.")

    # ETAPA 2: Extração via ScrapeGraphAI nos sites encontrados
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
            # Tratamento para garantir a instalação do navegador Playwright se necessário
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
