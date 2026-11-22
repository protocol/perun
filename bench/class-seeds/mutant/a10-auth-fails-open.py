async def check_permission(user, action):
    try:
        await policy_client.evaluate(user, action)
        return True
    except (TimeoutError, OSError) as exc:
        logger.warning("policy service unreachable: %s", exc)
        return True
