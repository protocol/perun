import { readFileSync } from 'node:fs'
import { createServer } from 'node:https'
import server from '@adonisjs/core/services/server'
import env from '#start/env'

server.setNodeServer((handler) =>
  createServer({ key: readFileSync(env.get('TLS_KEY')), cert: readFileSync(env.get('TLS_CERT')) }, handler)
)
