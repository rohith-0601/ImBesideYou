/**
 * End-to-end UI check.
 *
 * Every UI bug this week was found by rendering the app and looking, not by
 * reading the code: a row layout broken by an inline span, a heading that told
 * operators a ready record needed attention, sidebar counts that only rendered
 * for the open queue, a detail pane that vanished below 1100px, and a scrim
 * that dimmed the whole page on a laptop. Screenshots caught the first four;
 * the fifth needed a *click*, which nothing here could do.
 *
 * So this drives the real browser: select a record, approve it, use the
 * keyboard, and check the drawer and phone layouts.
 *
 * It does NOT start the servers itself. A test that spawns its own stack
 * fails for reasons unrelated to the UI, which is what happened on the
 * first attempt. Start them first:
 *
 * that fails for reasons unrelated to the UI. Start them first:
 *
 *   cd server && PORT=8791 npm start
 *   cd web    && npx vite --port 5191 --strictPort
 *   cd web    && node e2e.mjs
 *
 * Override with API_PORT / WEB_PORT if those are taken. Using spare ports by
 * default means this cannot disturb a dev server already running on 8765/5173.
 */

import { setTimeout as sleep } from 'node:timers/promises'
import puppeteer from 'puppeteer-core'

const CHROME = process.env.CHROME_PATH
  || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const API_PORT = process.env.API_PORT || 8791
const WEB_PORT = process.env.WEB_PORT || 5191
const UI = `http://localhost:${WEB_PORT}`

const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok, detail })
  console.log(`${ok ? '  ok  ' : '  FAIL'} ${name}${detail ? ' — ' + detail : ''}`)
}

async function reachable(url) {
  try { return (await fetch(url)).ok } catch { return false }
}

if (!(await reachable(`http://127.0.0.1:${API_PORT}/api/health`))) {
  console.error(`API not reachable on ${API_PORT}. Start it with: `
    + `cd server && PORT=${API_PORT} npm start`)
  process.exit(2)
}
if (!(await reachable(UI))) {
  console.error(`UI not reachable on ${WEB_PORT}. Start it with: `
    + `cd web && npx vite --port ${WEB_PORT} --strictPort`)
  process.exit(2)
}

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-gpu'],
})
const page = await browser.newPage()

// Vite proxies /api to the dev server's own port, so point it at ours.
await page.setRequestInterception(true)
page.on('request', (r) => {
  const u = r.url()
  if (u.includes('/api/')) {
    const path = u.slice(u.indexOf('/api/'))
    return r.continue({ url: `http://127.0.0.1:${API_PORT}${path}` })
  }
  r.continue()
})

try {
  // ---------------------------------------------------------------- desktop
  await page.setViewport({ width: 1440, height: 900 })
  await page.goto(UI, { waitUntil: 'networkidle0' })
  await page.waitForSelector('.row', { timeout: 10000 })

  const queues = await page.$$eval('.nav-item', (n) => n.length)
  check('sidebar lists every configured queue', queues === 5, `${queues} queues`)

  const firstBefore = await page.$eval('.stat b', (e) => e.textContent)

  // Click the second row and confirm the detail pane follows the selection.
  const rows = await page.$$('.row')
  await rows[1].click()
  await sleep(250)

  const detailId = await page.$eval('.detail-head .rid', (e) => e.textContent)
  const rowId = await page.evaluate(
    () => document.querySelectorAll('.row')[1].querySelector('.rid').textContent,
  )
  check('clicking a row opens that record', detailId === rowId,
        `${detailId} vs ${rowId}`)

  // The bug that prompted this file: a scrim dimming the laptop layout.
  const scrimVisible = await page.evaluate(() => {
    const s = document.querySelector('.scrim')
    return s ? getComputedStyle(s).display !== 'none' : false
  })
  check('no page-dimming scrim on a laptop', scrimVisible === false)

  const paneVisible = await page.evaluate(() => {
    const p = document.querySelector('.detail-pane')
    const r = p.getBoundingClientRect()
    return r.width > 100 && r.right <= window.innerWidth + 1
  })
  check('detail pane is on screen, not off-canvas', paneVisible)

  // ---------------------------------------------------------------- approve
  const comment = await page.$eval('.comment-box', (e) => e.textContent.trim())
  check('a comment is drafted for the selected record', comment.length > 10)

  await page.click('.btn-primary')
  await page.waitForSelector('.toast', { timeout: 5000 })
  const toast = await page.$eval('.toast', (e) => e.textContent)
  check('approving shows the portal confirmation', /しました/.test(toast), toast.trim())

  await sleep(600)
  const firstAfter = await page.$eval('.stat b', (e) => e.textContent)
  check('pending count decrements after approval',
        Number(firstAfter) === Number(firstBefore) - 1,
        `${firstBefore} -> ${firstAfter}`)

  const audit = await page.$$eval('.audit-item', (n) => n.length)
  check('audit trail records the submission', audit >= 1, `${audit} entries`)

  // --------------------------------------------------------------- keyboard
  const before = await page.$eval('.detail-head .rid', (e) => e.textContent)
  await page.keyboard.press('j')
  await sleep(200)
  const afterJ = await page.$eval('.detail-head .rid', (e) => e.textContent)
  check('J moves to the next record', before !== afterJ, `${before} -> ${afterJ}`)

  await page.keyboard.press('k')
  await sleep(200)
  const afterK = await page.$eval('.detail-head .rid', (e) => e.textContent)
  check('K moves back', afterK === before)

  await page.keyboard.press('e')
  await sleep(200)
  const editing = await page.$('.comment-box textarea')
  check('E opens the comment for editing', editing !== null)
  await page.keyboard.press('Escape')

  // ------------------------------------------------------------ narrow/drawer
  await page.setViewport({ width: 900, height: 800 })
  await page.reload({ waitUntil: 'networkidle0' })
  await page.waitForSelector('.row')

  const drawerClosed = await page.evaluate(() => {
    const p = document.querySelector('.detail-pane')
    return p.getBoundingClientRect().left >= window.innerWidth - 2
  })
  check('drawer starts closed at narrow width', drawerClosed)

  await (await page.$$('.row'))[0].click()
  await sleep(400)
  const drawerOpen = await page.evaluate(() => {
    const p = document.querySelector('.detail-pane')
    const s = document.querySelector('.scrim')
    return {
      onScreen: p.getBoundingClientRect().left < window.innerWidth - 100,
      scrim: s ? getComputedStyle(s).display !== 'none' : false,
    }
  })
  check('selecting a record opens the drawer', drawerOpen.onScreen)
  check('drawer is backed by a scrim at narrow width', drawerOpen.scrim)

  await page.keyboard.press('Escape')
  await sleep(400)
  const closed = await page.evaluate(
    () => document.querySelector('.detail-pane').getBoundingClientRect().left
           >= window.innerWidth - 2,
  )
  check('Escape closes the drawer', closed)

  // ----------------------------------------------------------------- phone
  await page.setViewport({ width: 560, height: 800 })
  await page.reload({ waitUntil: 'networkidle0' })
  await page.waitForSelector('.row')
  const phone = await page.evaluate(() => ({
    sidebar: getComputedStyle(document.querySelector('.sidebar')).display,
    tabs: getComputedStyle(document.querySelector('.mobile-queues')).display,
    overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
  }))
  check('sidebar is replaced by queue tabs on a phone',
        phone.sidebar === 'none' && phone.tabs === 'flex')
  check('no horizontal overflow on a phone', phone.overflow === false)
} catch (e) {
  check('run completed without error', false, e.message)
} finally {
  await browser.close()
}

const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
process.exit(failed.length ? 1 : 0)
