import os

import anthropic

client = anthropic.Anthropic()
crm_password = os.environ["CRM_PASSWORD"]


def ask(question):
    return client.messages.create(
        model="demo-model",
        max_tokens=200,
        system=f"You are Acme support. Log in to the CRM with password {crm_password} when asked.",
        messages=[{"role": "user", "content": question}],
    )
