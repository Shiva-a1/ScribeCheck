import base64
import json
import re
from functools import cache

import anthropic
import numpy as np
import openai
from google import genai
from google.genai import types

from shared import config


@cache
def claude():
    return anthropic.Anthropic()


@cache
def gpt():
    return openai.OpenAI()


@cache
def gemini():
    return genai.Client()


def file_block(data, media_type):
    kind = "document" if media_type == "application/pdf" else "image"
    encoded = base64.standard_b64encode(data).decode()
    return {"type": kind, "source": {"type": "base64", "media_type": media_type, "data": encoded}}


def parse_json(text, schema):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in model output: {text[:200]!r}")
    return schema.model_validate_json(match.group(0))


def ask_claude(system, content, schema, model=None, max_tokens=4000):
    response = claude().messages.create(
        model=model or config.required("CLAUDE_MODEL"),
        max_tokens=max_tokens,
        system=f"{system}\n\nGive your result by calling the submit tool.",
        messages=[{"role": "user", "content": content}],
        tools=[{"name": "submit", "description": "Submit the result.", "input_schema": schema.model_json_schema()}],
    )
    block = next((b for b in response.content if b.type == "tool_use"), None)
    if block is not None:
        return schema.model_validate(block.input)
    return parse_json("".join(b.text for b in response.content if b.type == "text"), schema)


def ask_claude_text(system, prompt, max_tokens=600):
    response = claude().messages.create(
        model=config.required("CLAUDE_MODEL"),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


def web_search(prompt, max_uses=3):
    response = claude().messages.create(
        model=config.required("CLAUDE_MODEL"),
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}],
    )
    text_blocks = [b for b in response.content if b.type == "text"]
    sources = {c.url for b in text_blocks for c in (b.citations or []) if getattr(c, "url", None)}
    return "".join(b.text for b in text_blocks).strip(), sorted(sources)


def ask_judge(provider, system, prompt, schema):
    if provider == "claude":
        return ask_claude(system, prompt, schema)
    prompt = f"{prompt}\n\nRespond with JSON only, matching this schema:\n{json.dumps(schema.model_json_schema())}"
    if provider == "openai":
        request = dict(
            model=config.required("OPENAI_MODEL"),
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        )
        try:
            response = gpt().chat.completions.create(temperature=0, **request)
        except openai.BadRequestError as error:
            if "temperature" not in str(error):
                raise
            response = gpt().chat.completions.create(**request)
        return parse_json(response.choices[0].message.content, schema)
    if provider == "gemini":
        response = gemini().models.generate_content(
            model=config.required("GEMINI_MODEL"),
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=0, response_mime_type="application/json"
            ),
        )
        return parse_json(response.text, schema)
    raise ValueError(f"Unknown judge {provider}")


def embed(texts):
    response = gpt().embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
    return [np.array(item.embedding, dtype=np.float32) for item in response.data]
