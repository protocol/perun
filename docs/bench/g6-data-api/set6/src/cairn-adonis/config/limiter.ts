import env from '#start/env'
import { defineConfig, stores } from '@adonisjs/limiter'

export default defineConfig({
  default: env.get('LIMITER_STORE'),
  stores: {
    memory: stores.memory({}),
  },
})
