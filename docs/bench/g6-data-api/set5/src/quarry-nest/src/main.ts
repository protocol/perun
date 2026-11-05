import { NestFactory } from '@nestjs/core'
import cookieParser from 'cookie-parser'
import { AppModule } from './app.module'

async function main() {
  const app = await NestFactory.create(AppModule, { logger: ['log', 'warn', 'error'] })
  app.use(cookieParser())
  await app.listen(3000, '127.0.0.1')
}

main()
