import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from scrapegraphai.graphs import SmartScraperGraph
from dotenv import load_dotenv

load_dotenv()

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
async def scrape_site(request: ScrapeRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Chave OPENAI_API_KEY não configurada no servidor.")

    # Se a entrada não for uma URL (http/https), transforma em busca no Google Maps
    if not request.url.startswith("http://") and not request.url.startswith("https://"):
        termo_busca = request.url.replace(" ", "+")
        source_url = f"https://www.google.com/maps/search/{termo_busca}"
    else:
        source_url = request.url

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
            prompt=request.prompt,
            source=source_url,
            config=graph_config
        )
        result = smart_scraper.run()
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
