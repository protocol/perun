import { defineConfig } from '@adonisjs/core/app'

export default defineConfig({
  commands: [() => import('@adonisjs/core/commands')],
  providers: [
    () => import('@adonisjs/core/providers/app_provider'),
    {
      file: () => import('@adonisjs/core/providers/repl_provider'),
      environment: ['repl', 'test'],
    },
    () => import('@adonisjs/limiter/limiter_provider'),
  ],
  preloads: [
    () => import('#start/routes'),
    () => import('#start/kernel'),
    () => import('#start/tls'),
  ],
})
