import { Module } from '@nestjs/common'
import { OrdersController } from './orders.controller'
import { AccountsController } from './accounts.controller'
import { BillingController } from './billing.controller'
import { NotesController } from './notes.controller'
import { ReportsController } from './reports.controller'
import { SupportController } from './support.controller'
import { StatusController } from './status.controller'

@Module({
  controllers: [StatusController, OrdersController, AccountsController, BillingController, NotesController, ReportsController, SupportController],
})
export class AppModule {}
