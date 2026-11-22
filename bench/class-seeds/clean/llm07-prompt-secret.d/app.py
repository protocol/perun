import anthropic

client = anthropic.Anthropic()


def lookup_crm(account_id):
    return {"account": account_id}  # server-side tool holds the credential


def ask(question):
    return client.messages.create(
        model="demo-model",
        max_tokens=200,
        system="You are Acme support. Use the lookup tool for CRM questions.",
        messages=[{"role": "user", "content": question}],
    )
