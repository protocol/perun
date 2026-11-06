import { Env } from '@adonisjs/core/env'

export default await Env.create(new URL('../', import.meta.url), {
  NODE_ENV: Env.schema.enum(['development', 'production', 'test'] as const),
  PORT: Env.schema.number(),
  HOST: Env.schema.string({ format: 'host' }),
  APP_KEY: Env.schema.string(),
  LOG_LEVEL: Env.schema.string(),
  LIMITER_STORE: Env.schema.enum(['memory'] as const),
  TLS_KEY: Env.schema.string(),
  TLS_CERT: Env.schema.string(),
  CAIRN_VENDOR_KEY: Env.schema.string.optional(),
})
