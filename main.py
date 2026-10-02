import os
import subprocess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from scrapegraphai.graphs import SmartScraperGraph
from googlesearch import search
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

    # ETAPA 1: Se for termo de busca/nicho, pesquisa no Google e obtém os links dos sites oficiais
    if not request.url.startswith("http://") and not request.url.startswith("https://"):
        try:
            # Busca os 3 primeiros sites reais no Google (evitando agregadores genéricos)
            query = f"{request.url} site oficial"
            search_results = search(query, num_results=5, lang="pt")
            
            for url_found in search_results:
                # Ignora redes sociais ou sites de busca genéricos
                if not any(domain in url_found for domain in ["google.com", "instagram.com", "facebook.com", "linkedin.com", "youtube.com"]):
                    targets.append(url_found)
                if len(targets) >= 3: # Limita aos 3 primeiros sites para não estourar o tempo de resposta
                    break
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao buscar sites no Google: {str(e)}")
    else:
        targets.append(request.url)

    if not targets:
        raise HTTPException(status_code=404, detail="Nenhum site oficial foi encontrado para este termo de busca.")

    # ETAPA 2: Para cada site encontrado, roda o ScrapeGraphAI na URL
    all_leads = []
    
    prompt_detalhado = (
        f"{request.prompt}\n\n"
        "Análise o site corporativo e extraia as seguintes informações no formato JSON:\n"
        "- nome_empresa: Nome oficial da empresa\n"
        "- telefone: Telefone fixo, celular ou WhatsApp de contato\n"
        "- email: E-mail corporativo ou de contato/atendimento encontrado no site\n"
        "- endereco: Endereço físico da empresa (rua, bairro, cidade)\n"
        "- responsavel: Nome do diretor, fundador, sócio ou gestor (se mencionado na página sobre/equipe)\n"
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
            # Caso falhe o navegador em algum site, tenta reinstalar Chromium se necessário
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
