import { describe, expect, it } from 'vitest'
import { buildProjectModuleSearchParams, ensureChapterSearchParams, resolveProjectModule } from '../project-routing'

describe('project routing helpers', () => {
  it('keeps current chapter when switching to the workbench menu item', () => {
    const next = buildProjectModuleSearchParams(
      new URLSearchParams('chapter=4&view=workflow&auto_generate=1'),
      'overview',
      4
    )

    expect(next.get('module')).toBe('overview')
    expect(next.get('chapter')).toBe('4')
    expect(next.get('view')).toBeNull()
    expect(next.get('auto_generate')).toBeNull()
  })

  it('keeps chapter sub-view only inside the chapter writing module', () => {
    const next = buildProjectModuleSearchParams(
      new URLSearchParams('chapter=4&view=workflow'),
      'chapters',
      4
    )

    expect(next.get('module')).toBe('chapters')
    expect(next.get('chapter')).toBe('4')
    expect(next.get('view')).toBe('workflow')
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

  it('defaults project root to overview instead of chapter writing', () => {
    expect(resolveProjectModule(new URLSearchParams(''))).toBe('overview')
  })

  it('keeps legacy chapter links in chapter writing mode', () => {
    expect(resolveProjectModule(new URLSearchParams('chapter=1'))).toBe('chapters')
  })

  it('honors explicit modules even when chapter context exists', () => {
    expect(resolveProjectModule(new URLSearchParams('module=genesis&chapter=1'))).toBe('genesis')
  })
})
