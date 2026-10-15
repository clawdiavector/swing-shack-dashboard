import { describe, expect, it } from 'vitest'
import { dueWords, groupTodo, stepLabel, todoSummary, type TodoStep } from './planTodo'

const s = (key: string, bucket: TodoStep['bucket'], over: Partial<TodoStep> = {}): TodoStep => ({
  key,
  brand_id: 'stick',
  plan_id: 'pln-1',
  item_id: key,
  step: 'post',
  title: 'A post',
  due: '2026-10-14',
  days: 0,
  bucket,
  event_name: "Valentine's Day",
  event_date: '2027-02-14',
  event_kind: 'retail_push',
  plan_status: 'proposed',
  needs: [],
  ...over,
})

describe('groupTodo', () => {
  it('keeps every bucket, in the order the page shows them', () => {
    const g = groupTodo([s('a', 'later'), s('b', 'overdue'), s('c', 'overdue')])
    expect(Object.keys(g)).toEqual(['overdue', 'today', 'this_week', 'later'])
    expect(g.overdue.map((x) => x.key)).toEqual(['b', 'c'])
    expect(g.today).toEqual([])
  })
})

describe('dueWords', () => {
  it('says it the way a person would', () => {
    expect(dueWords(0)).toBe('today')
    expect(dueWords(1)).toBe('tomorrow')
    expect(dueWords(-1)).toBe('yesterday')
    expect(dueWords(5)).toBe('in 5 days')
    expect(dueWords(-4)).toBe('4 days ago')
  })
})

describe('todoSummary', () => {
  it('leads with what is overdue and due today', () => {
    expect(todoSummary({ overdue: 2, today: 1, this_week: 4, later: 9 })).toBe('2 overdue, 1 due today, 4 more this week.')
    expect(todoSummary({ overdue: 0, today: 0, this_week: 3, later: 1 })).toBe('3 more this week.')
    expect(todoSummary({ overdue: 0, today: 0, this_week: 0, later: 5 })).toBe('Nothing is overdue or due today.')
  })
})

describe('stepLabel', () => {
  it('uses the step names people see in the plan', () => {
    expect(stepLabel(s('a', 'today', { step: 'review' }))).toBe('Approve')
    expect(stepLabel(s('a', 'today', { step: 'shoot' }))).toBe('Shoot')
  })
})
