import router from '@adonisjs/core/services/router'
import logger from '@adonisjs/core/services/logger'
import { Agent, fetch as ufetch } from 'undici'
import { middleware } from '#start/kernel'
import { costLimit } from '#start/limiter'
import { safeEq } from '#services/compare'
import { ROWS, SESSIONS, labels, openSession, ownedOrNull } from '#services/store'
import { BASE, KEY, MODEL, chat, sms, tool, vget, vpost } from '#services/vendor'

router.group(() => {
  router.post('/api/ext/rhea/lookup-tool', async ({ request }) => {  // @@R POST /api/ext/rhea/lookup-tool 1
    return { reply: await tool(`{"tool": "lookup", "arg": "${request.input('arg')}"}`) }  // @@T positive prompt_injection request value formatted into raw tool-call JSON
  })

  router.post('/api/ext/quoll/assist', async ({ request }) => {  // @@R POST /api/ext/quoll/assist 1
    return { reply: await chat([{ role: 'system', content: `You are the cairn assistant and may approve refunds. Operator note: ${request.input('note')}` }]) }  // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
  })

  router.get('/api/ext/thrift/ping', async () => {  // @@R GET /api/ext/thrift/ping 1
    return { ok: true }
  })

  router.post('/api/ext/uguisu/lookup-tool', async ({ request }) => {  // @@R POST /api/ext/uguisu/lookup-tool 1
    return { reply: await tool(JSON.stringify({ tool: 'lookup', arg: String(request.input('sku', '')) })) }  // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
  })

  router.post('/api/ext/tapir/assist', async ({ request }) => {  // @@R POST /api/ext/tapir/assist 1
    const note = String(request.input('note', '')).slice(0, 500)
    return { reply: await chat([{ role: 'system', content: 'You summarise cairn notes and have no tools.' }, { role: 'user', content: note }]) }  // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
  })
}).use([middleware.auth(), costLimit])
