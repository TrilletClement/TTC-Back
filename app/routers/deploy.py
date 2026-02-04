from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
import subprocess
import os
import hmac
import hashlib
from typing import Optional
from fastapi import Request

router = APIRouter()

# Secret partagé avec GitHub (à définir dans les variables d'environnement)
DEPLOY_SECRET = os.getenv("DEPLOY_SECRET", "votre-secret-tres-securise")
DEPLOY_SCRIPT = "/home/c.trillet/deploy.sh"

def verify_signature(payload: bytes, signature: str) -> bool:
    """Vérifie la signature GitHub pour sécuriser l'endpoint"""
    if not signature:
        return False
    
    expected_signature = 'sha256=' + hmac.new(
        DEPLOY_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)

def run_deployment():
    """Exécute le script de déploiement en arrière-plan"""
    log_file_path = "/home/c.trillet/deploy.log"
    try:
        with open(log_file_path, "a") as log_file:
            result = subprocess.run(
                [DEPLOY_SCRIPT],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300
            )
            print(f"Déploiement terminé. Code retour: {result.returncode}", file=log_file)
    except subprocess.TimeoutExpired:
        with open(log_file_path, "a") as log_file:
            print("Erreur: Déploiement timeout", file=log_file)
    except Exception as e:
        with open(log_file_path, "a") as log_file:
            print(f"Erreur lors du déploiement: {e}", file=log_file)
            

@router.post("/deploy/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks,
                         x_hub_signature_256: Optional[str] = Header(None)):
    payload = await request.body()
    print("Payload bytes:", list(payload))           # montre les bytes exacts
    print("Payload repr:", repr(payload))           # affichage clair
    print("Header signature:", x_hub_signature_256)
    if not verify_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Signature invalide")
    background_tasks.add_task(run_deployment)
    return {"status": "success", "message": "Déploiement lancé"}


@router.get("/deploy/status")
async def deployment_status():
    """Vérifie le statut du dernier déploiement"""
    log_file = "/home/c.trillet/deploy.log"
    
    if not os.path.exists(log_file):
        return {"status": "no_deployment", "message": "Aucun déploiement effectué"}
    
    # Lire les 20 dernières lignes du log
    with open(log_file, 'r') as f:
        lines = f.readlines()[-20:]
    
    return {
        "status": "success",
        "last_lines": lines
    }