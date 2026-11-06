import 'reflect-metadata'
import { Ignitor } from '@adonisjs/core'

const APP_ROOT = new URL('../', import.meta.url)

new Ignitor(APP_ROOT, { importer: (filePath) => import(filePath) })
  .tap((app) => {
    app.booting(async () => {
      await import('#start/env')
    })
  })
  .httpServer()
  .start()
