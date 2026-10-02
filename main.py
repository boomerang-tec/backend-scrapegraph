import os
import subprocess
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
    return {"message": "API ScrapeGraphAI está online!"}

@app.post("/scrape")
def scrape_site(request: ScrapeRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Chave OPENAI_API_KEY não configurada no servidor.")

    # Se a entrada for termo de busca/nicho, direciona para a pesquisa
    if not request.url.startswith("http://") and not request.url.startswith("https://"):
        termo_busca = request.url.replace(" ", "+")
        source_url = f"https://www.google.com/maps/search/{termo_busca}"
    else:
        source_url = request.url

    # Prompt otimizado para enriquecimento de Leads
    prompt_detalhado = (
        f"{request.prompt}\n\n"
        "Extraia todos os estabelecimentos/empresas encontrados na página. "
        "Para cada empresa, identifique rigorosamente os seguintes campos no formato JSON:\n"
        "- nome_empresa: Nome do estabelecimento\n"
        "- telefone: Número de telefone ou WhatsApp de contato com DDD\n"
        "- email: Endereço de e-mail (se disponível)\n"
        "- endereco: Endereço completo ou bairro/cidade\n"
        "- responsavel: Nome do proprietário, diretor, gestor ou contato principal (se mencionado)\n"
        "- website: URL do site oficial da empresa (se disponível)\n"
        "Retorne APENAS um array de objetos JSON contendo essas informações."
    )

    graph_config = {
        "llm": {
            "api_key": api_key,
            "model": "gpt-4o-mini",
        },
        "verbose": True,
        "headless": True,
    }

    try:
        smart_scraper = SmartScraperGraph(
            prompt=prompt_detalhado,
            source=source_url,
            config=graph_config
        )
        result = smart_scraper.run()
        
        # Garante o envio de uma estrutura consistente para o Lovable
        return {"success": True, "leads": result}
    except Exception as e:
        if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
            try:
                subprocess.run(["playwright", "install", "chromium"], check=True)
                smart_scraper = SmartScraperGraph(
                    prompt=prompt_detalhado,
                    source=source_url,
                    config=graph_config
                )
                result = smart_scraper.run()
                return {"success": True, "leads": result}
            except Exception as retry_err:
                raise HTTPException(status_code=500, detail=f"Erro ao reinstalar Chromium: {str(retry_err)}")
        
        raise HTTPException(status_code=500, detail=str(e))
