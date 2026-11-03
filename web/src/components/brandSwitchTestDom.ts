import { Window } from 'happy-dom'

const win = new Window({ url: 'http://localhost/app/daily' })
const g = globalThis as unknown as Record<string, unknown>
g.window = win
g.document = win.document
g.localStorage = win.localStorage
g.sessionStorage = win.sessionStorage
g.HTMLElement = win.HTMLElement
g.Element = win.Element
g.Node = win.Node
g.DocumentFragment = win.DocumentFragment
g.MutationObserver = win.MutationObserver
g.Event = win.Event
g.MouseEvent = win.MouseEvent
g.getComputedStyle = win.getComputedStyle.bind(win)
g.IS_REACT_ACT_ENVIRONMENT = true
g.requestAnimationFrame = (cb: FrameRequestCallback) => setTimeout(() => cb(Date.now()), 0)
g.cancelAnimationFrame = (id: number) => clearTimeout(id as unknown as ReturnType<typeof setTimeout>)
