/**
 * D1 database binding helper.
 *
 * Usage in a route handler:
 *   import { DB } from '../db'
 *   const db = DB(c.env)
 *   const { results } = await db.all("SELECT ...", [param])
 *   const row = await db.one("SELECT ...", [param])
 *   const info = await db.run("INSERT ...", [param])
 */

export type Env = {
  DB: D1Database
  ADMIN_API_KEY?: string
}

export function DB(env: Env) {
  return new D1Helpers(env.DB)
}

class D1Helpers {
  constructor(private db: D1Database) {}

  /** Fetch multiple rows. Returns typed results array. */
  all<T = Record<string, unknown>>(sql: string, ...bind: unknown[]) {
    return this.db.prepare(sql).bind(...bind).all<T>()
  }

  /** Fetch one row or null. */
  async one<T = Record<string, unknown>>(sql: string, ...bind: unknown[]) {
    const result = await this.db.prepare(sql).bind(...bind).first<T>()
    return (result as T) ?? null
  }

  /** Execute a write statement. Returns D1Result. */
  run(sql: string, ...bind: unknown[]) {
    return this.db.prepare(sql).bind(...bind).run()
  }

  /** Execute raw SQL (multi-statement, no bindings). */
  exec(sql: string) {
    return this.db.exec(sql)
  }

  /** Batch multiple prepared statements in a transaction. */
  batch(statements: { sql: string; bind?: unknown[] }[]) {
    const stmts = statements.map((s) => this.db.prepare(s.sql).bind(...(s.bind ?? [])))
    return this.db.batch(stmts)
  }
}
