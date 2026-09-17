"""
gemma_client.py
---------------
Client minimal pour appeler le modèle Gemma auto-hébergé via vLLM
(endpoint compatible OpenAI /v1/chat/completions).

IMPORTANT — sécurité :
- Ne JAMAIS coder la clé API en dur dans ce fichier ou dans un autre script.
  Elle doit venir d'une variable d'environnement (GEMMA_API_KEY).
- Si la clé qui a servi lors des tests a été partagée quelque part (chat,
  ticket, etc.), il faut la régénérer côté infra avant de mettre ce code
  en prod.

Configuration attendue (variables d'environnement) :
    GEMMA_API_URL   (optionnel, valeur par défaut = endpoint interne connu)
    GEMMA_API_KEY   (obligatoire)
    GEMMA_MODEL     (optionnel, défaut = "gemma-4-31B")
    GEMMA_VERIFY_SSL (optionnel, "true"/"false", défaut "false" car l'endpoint
                       interne utilisé pendant les tests avait un certificat
                       non standard -- cf. le "-k" dans le curl d'origine)
"""

import os
import json
import re
from typing import List, Dict, Any, Optional

import requests
import urllib3

GEMMA_API_URL = os.environ.get(
    "GEMMA_API_URL",
    "https://vllm-gemma4-31b-mtrna-ns1.apps.olympus.atlasxai.ma/v1/chat/completions",
)
GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-31B")
GEMMA_VERIFY_SSL = os.environ.get("GEMMA_VERIFY_SSL", "false").lower() == "true"

# On sait déjà que le endpoint interne utilise un certificat non standard
# (d'où le "-k" dans le curl d'origine) -- inutile de spammer la console
# avec un warning à chaque appel si on a choisi consciemment de ne pas
# vérifier le certificat.
if not GEMMA_VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Valeur par défaut codée en dur pour aller vite en test local.
# Une variable d'environnement GEMMA_API_KEY, si elle est définie, prend
# toujours le dessus sur cette valeur (voir _get_api_key ci-dessous).
# ATTENTION : si ce fichier part sur un dépôt Git partagé ou un serveur,
# cette clé devient visible à toute personne qui y a accès -- il faudra la
# régénérer côté infra avant tout partage/déploiement.
_DEFAULT_GEMMA_API_KEY = "91eb20660c62920a5ebee5ab782659923c5077b858b2dd1545f978d02eb63084"


class GemmaClientError(Exception):
    """Erreur générique lors d'un appel au modèle Gemma."""


def _get_api_key() -> str:
    api_key = os.environ.get("GEMMA_API_KEY", _DEFAULT_GEMMA_API_KEY)
    if not api_key:
        raise GemmaClientError(
            "Aucune clé API Gemma disponible. Définis GEMMA_API_KEY ou "
            "_DEFAULT_GEMMA_API_KEY dans gemma_client.py."
        )
    return api_key


def call_gemma(
    messages: List[Dict[str, str]],
    temperature: float = 0.0,
    max_tokens: int = 300,
    timeout: int = 30,
) -> str:
    """
    Appelle le endpoint chat/completions et renvoie le texte de la réponse
    (content du premier choix). Lève GemmaClientError en cas de problème
    réseau/API pour que l'appelant décide comment gérer l'échec.
    """
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GEMMA_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        response = requests.post(
            GEMMA_API_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
            verify=GEMMA_VERIFY_SSL,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise GemmaClientError(f"Erreur réseau/API en appelant Gemma : {e}") from e

    try:
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise GemmaClientError(f"Réponse Gemma inattendue : {e} -- brut: {response.text[:300]}") from e


def extract_json_object(raw_text: str) -> Dict[str, Any]:
    """
    Les modèles renvoient parfois le JSON entouré de ```json ... ``` ou de
    texte parasite. Cette fonction essaie d'extraire un objet JSON valide
    de façon tolérante.
    """
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError(f"Impossible d'extraire un JSON de la réponse : {raw_text[:300]}")