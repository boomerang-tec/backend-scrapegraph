import os
import asyncio
import urllib.parse
import subprocess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from scrapegraphai.graphs import SmartScraperGraph
from playwright.async_api import async_playwright
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
    return {"message": "API ScrapeGraphAI Online"}

async def buscar_urls_playwright_async(termo: str) -> list:
    print(f"\n[ESTÁGIO 1] A iniciar pesquisa via Playwright para: '{termo}'", flush=True)
    targets = []
    dominios_ignorados = [
        "google.", "instagram.com", "facebook.com", "linkedin.com",
        "youtube.com", "wikipedia.org", "duckduckgo.com", "twitter.com",
        "x.com", "pinterest.com", "tiktok.com", "tripadvisor.com",
        "yellowpages.com", "guiamais.com.br", "apontador.com.br"
    ]

    query_encoded = urllib.parse.quote_plus(termo)
    search_url = f"https://html.duckduckgo.com/html/?q={query_encoded}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            print(f"[ESTÁGIO 1] A navegar para a página de pesquisa...", flush=True)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
            
            # Obtém os links dos resultados
            elements = await page.query_selector_all("a.result__url")
            for elem in elements:
                href = await elem.get_attribute("href")
                if href:
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
        except Exception as e:
            print(f"[ERRO ESTÁGIO 1]: {str(e)}", flush=True)
        finally:
            await browser.close()

    print(f"[ESTÁGIO 1 FINALIZADO] URLs encontradas: {len(targets)}", flush=True)
    return targets

@app.post("/scrape")
async def scrape_site(request: ScrapeRequest):
    print(f"\n================ NOVA REQUISIÇÃO /SCRAPE ================", flush=True)
    print(f"Entrada recebida: '{request.url}'", flush=True)

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("[ERRO]: OPENAI_API_KEY não configurada!", flush=True)
        raise HTTPException(status_code=500, detail="Chave OPENAI_API_KEY não configurada no servidor.")

    targets = []

    if not request.url.startswith("http://") and not request.url.startswith("https://"):
        targets = await buscar_urls_playwright_async(request.url)
    else:
        targets.append(request.url)

    if not targets:
        print("[FALHA]: Nenhuma URL capturada no Estágio 1.", flush=True)
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

    print(f"[ESTÁGIO 2] A processar {len(targets)} site(s) com ScrapeGraphAI...", flush=True)

    # Executa a raspagem síncrona dentro do loop num executor para não bloquear a thread
    loop = asyncio.get_event_loop()
    for idx, site_url in enumerate(targets, 1):
        print(f"   [{idx}/{len(targets)}] A extrair dados de: {site_url}", flush=True)
        
        def run_scraper(url):
            smart_scraper = SmartScraperGraph(
                prompt=prompt_detalhado,
                source=url,
                config=graph_config
            )
            return smart_scraper.run()

        try:
            result = await loop.run_in_executor(None, run_scraper, site_url)
            if result and isinstance(result, dict):
                result["website"] = site_url
                all_leads.append(result)
                print(f"   [SUCESSO]: Dados extraídos de {site_url}", flush=True)
        except Exception as e:
            print(f"   [ERRO ao raspar {site_url}]: {str(e)}", flush=True)

    print(f"================ REQUISIÇÃO FINALIZADA (Leads: {len(all_leads)}) ================\n", flush=True)
    return {"success": True, "total": len(all_leads), "leads": all_leads}
