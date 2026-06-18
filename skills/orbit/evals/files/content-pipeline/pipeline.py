"""Run-by-hand content pipeline: topic -> outline -> draft. No memory, no checks, no caps."""
import os
import requests

API_KEY = os.environ.get("MODEL_API_KEY", "")
CMS_TOKEN = os.environ.get("CMS_TOKEN", "")


def call_model(prompt: str) -> str:
    r = requests.post(
        "https://api.example-llm.com/v1/generate",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"prompt": prompt},
    )
    return r.json()["text"]


def draft_post(topic: str) -> str:
    outline = call_model(f"Outline a blog post about: {topic}")
    draft = call_model(f"Write the full post from this outline:\n{outline}")
    return draft  # no fact-check, no editor pass


def publish(markdown: str):
    """Pushes straight to the live CMS. No human review."""
    requests.post(
        "https://cms.example.com/api/posts",
        headers={"Authorization": f"Bearer {CMS_TOKEN}"},
        json={"status": "published", "body": markdown},
    )


if __name__ == "__main__":
    post = draft_post("How fluid compute reduces cold starts")
    print(post)
