import { describe, expect, it } from 'vitest'
import { buildProjectModuleSearchParams, ensureChapterSearchParams } from '../project-routing'

describe('project routing helpers', () => {
  it('keeps current chapter when switching to the workbench menu item', () => {
    const next = buildProjectModuleSearchParams(
      new URLSearchParams('chapter=4&view=workflow&auto_generate=1'),
      'overview',
      4
    )

    expect(next.get('module')).toBe('overview')
    expect(next.get('chapter')).toBe('4')
    expect(next.get('view')).toBe('workflow')
    expect(next.get('auto_generate')).toBeNull()
  })

  it('keeps chapter context while switching to project data modules', () => {
    const next = buildProjectModuleSearchParams(
      new URLSearchParams('chapter=5&view=artifacts'),
      'outline',
      5
    )

    expect(next.get('module')).toBe('outline')
    expect(next.get('chapter')).toBe('5')
    expect(next.get('view')).toBeNull()
  })

  it('fills missing chapter without forcing the module back to chapters', () => {
    const next = ensureChapterSearchParams(new URLSearchParams('module=overview'), 3)

    expect(next.get('module')).toBe('overview')
    expect(next.get('chapter')).toBe('3')
  })
})
