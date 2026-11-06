import env from '#start/env'
import { defineConfig, targets } from '@adonisjs/core/logger'

export default defineConfig({
  default: 'app',
  loggers: {
    app: {
      enabled: true,
      name: 'cairn',
      level: env.get('LOG_LEVEL', 'info'),
      transport: { targets: [targets.file({ destination: 1 })] },
    },
  },
})
