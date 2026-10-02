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
    return {"message": "API ScrapeGraphAI em 2 Etapas está online!"}

@app.post("/scrape")
def scrape_site(request: ScrapeRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Chave OPENAI_API_KEY não configurada no servidor.")

    targets = []

    # ETAPA 1: Se for termo de busca, busca URLs
    if not request.url.startswith("http://") and not request.url.startswith("https://"):
        try:
            with DDGS() as ddgs_client:
                # Busca direta
                results = list(ddgs_client.text(request.url, max_results=10))
                
                for r in results:
                    url_found = r.get("href", "")
                    if not any(domain in url_found for domain in ["google.com", "instagram.com", "facebook.com", "linkedin.com", "youtube.com", "duckduckgo.com", "wikipedia.org"]):
                        targets.append(url_found)
                    if len(targets) >= 3:
                        break
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao realizar busca: {str(e)}")
    else:
        targets.append(request.url)

    if not targets:
        raise HTTPException(status_code=404, detail="Nenhum site oficial foi encontrado para o termo pesquisado.")

    # ETAPA 2: Extração via ScrapeGraphAI
    all_leads = []
    
    prompt_detalhado = (
        f"{request.prompt}\n\n"
        "Analise o site corporativo e extraia as seguintes informações no formato JSON:\n"
        "- nome_empresa: Nome oficial da empresa\n"
        "- telefone: Telefone fixo, celular ou WhatsApp de contato\n"
        "- email: E-mail corporativo ou de contato/atendimento encontrado no site\n"
        "- endereco: Endereço físico da empresa (rua, bairro, cidade)\n"
        "- responsavel: Nome do diretor, fundador, sócio ou gestor (se mencionado)\n"
        "- website: A própria URL do site que foi analisado\n"
        "Retorne APENAS um objeto JSON com esses campos."
    )

    graph_config = {
        "llm": {
            "api_key": api_key,
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
            if result:
                if isinstance(result, dict):
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
                if result:
                    all_leads.append(result)

    return {"success": True, "total": len(all_leads), "leads": all_leads}
