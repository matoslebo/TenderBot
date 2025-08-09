# app/llm/providers.py (ROZŠÍRENIE)
import os
from typing import Optional, Dict, Any

try:
    import litellm  # type: ignore
except Exception:
    litellm = None

LLM_PROVIDER = os.getenv("LLM_MODEL_PROVIDER")
LLM_MODEL = os.getenv("LLM_MODEL_NAME")

def has_llm() -> bool:
    return litellm is not None and LLM_PROVIDER and LLM_MODEL

def _model_id() -> str:
    return f"{LLM_PROVIDER}/{LLM_MODEL}"

def generate_answer(prompt: str, system: Optional[str] = None) -> str:
    if not has_llm():
        return f"[dry-run] Bez LLM: Vstupný prompt bol:\n{prompt[:800]}"
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    try:
        resp = litellm.completion(model=_model_id(), messages=msgs)
        return resp.choices[0].message["content"]
    except Exception as e:
        return f"[LLM error] {e}"

def generate_json(
    prompt: str,
    system: Optional[str] = None,
    schema: Dict[str, Any] | None = None,
    enforce_json: bool = True
) -> str:
    """
    Požiada LLM o JSON výstup. Ak provider podporuje 'response_format',
    použije ho; inak padne do fallbacku (silná inštrukcia 'iba JSON').
    """
    if not has_llm():
        return '{"note":"dry-run; no LLM configured"}'

    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    # Fallback inštrukcia pre modely bez native JSON režimu
    if not schema:
        prompt2 = prompt + "\n\nPokyny:\n- Vráť IBA platný JSON objekt bez komentárov.\n- Žiadny text pred/za JSON-om."
    else:
        prompt2 = prompt
    msgs.append({"role": "user", "content": prompt2})

    kwargs = {}
    # Skús „native“ JSON enforcement where available (OpenAI, Azure OpenAI, atď.)
    if enforce_json:
        if schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "ExtractionOut",
                    "schema": schema
                }
            }
        else:
            kwargs["response_format"] = {"type": "json_object"}

    try:
        resp = litellm.completion(model=_model_id(), messages=msgs, **kwargs)
        return resp.choices[0].message["content"]
    except Exception:
        # Fallback: bez response_format
        resp = litellm.completion(model=_model_id(), messages=msgs)
        return resp.choices[0].message["content"]
