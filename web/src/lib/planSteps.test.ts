import { describe, expect, it } from 'vitest'
import { planStatusLine, stepChipLabel, stepWhen, stepsByDay, type PlanStep } from './planSteps'

const s = (key: string, date: string, over: Partial<PlanStep> = {}): PlanStep => ({
  key,
  plan_id: 'pln-1',
  item_id: key,
  title: 'Shoot real photos',
  step: 'shoot',
  date,
  late: false,
  channel: '',
  event_name: "Valentine's Day",
  event_date: '2027-02-14',
  event_kind: 'retail_push',
  plan_status: 'proposed',
  ...over,
})

describe('stepsByDay', () => {
  it('puts each step on the day it is due', () => {
    const g = stepsByDay([s('a', '2027-02-02'), s('b', '2027-02-02'), s('c', '2027-02-05')])
    expect(Object.keys(g)).toEqual(['2027-02-02', '2027-02-05'])
    expect(g['2027-02-02']).toHaveLength(2)
  })
})

describe('labels', () => {
  it('names the step and the date it is for', () => {
    expect(stepChipLabel(s('a', '2027-02-02'))).toBe("Shoot · Valentine's Day")
    expect(stepWhen(s('a', '2027-02-02'))).toBe("2 Feb 2027 · for Valentine's Day on 14 Feb 2027")
  })
  it('says where the plan has got to', () => {
    expect(planStatusLine(s('a', '2027-02-02'))).toMatch(/Draft plan/)
    expect(planStatusLine(s('a', '2027-02-02', { plan_status: 'approved' }))).toMatch(/not on the calendar yet/)
  })
})
